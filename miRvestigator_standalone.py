#################################################################
# @Program: miRvestigator_standalone.py                         #
# @Version: 1                                                   #
# @Author: Chris Plaisier                                       #
# @Sponsored by:                                                #
# Nitin Baliga, ISB                                             #
# Institute for Systems Biology                                 #
# 1441 North 34th Street                                        #
# Seattle, Washington  98103-8904                               #
# (216) 732-2139                                                #
# @Also Sponsored by:                                           #
# Luxembourg Systems Biology Grant                              #
#                                                               #
# If this program is used in your analysis please mention who   #
# built it. Thanks. :-)                                         #
#                                                               #
# Copyrighted by Chris Plaisier  4/14/2011                      #
#################################################################

# Libraries needed to run
import sys, re, os, math, shutil
from subprocess import *
from copy import deepcopy
from random import sample
import cPickle
from math import log
from sys import stdout
import re
import unicodedata

# https://github.com/zacharyvoase/slugify/blob/master/src/slugify.py
def slugify(string):
    return re.sub(r'[-\s]+', '-',
            unicode(
                re.sub(r'[^\w\s-]', '',
                    unicodedata.normalize('NFKD', unicode(string))
                    .encode('ascii', 'ignore'))
                .strip()
                .lower()))

# A class designed to compute and hold the information from analyzing
# miRNA seeds against motifs from 3' UTRs.
#
# Variables:
# miRNAver - version of miRBase.org used.
# miRNAs - list of miRNAs where each entry is unique, and names are appened for overlapping seeds.
# permKMers - list of possible Kmers given the seed length.
# 
# 
# Functions:
# addSorted(curList,newItem) - adds an entry into miRNAScores[pssm] so that the list is sorted in the end. Ties are possible and not handled at this level.
# allKmers(length) - creates a list of all possible Kmers given a specific length and alphabet.
# setMiRNAs(seedStart,seedEnd) - gets miRNAs from miRBase.org from the latest release.
# getTopHit(pssm.getName()) - gets top hit for a PSSM.
# getScoreList(pssm.getName()) - returns scores for all miRNA seeds for given PSSM, sorted of course.
#
class miRvestigator:
    # Initialize and start the run
    def __init__(self,pssms,seedModel=[6,7,8], minor=True, p5=True, p3=True, textOut=True, wobble=True, wobbleCut=0.25,species='hsa'):
        print '\nmiRvestigator analysis started...'
        self.pssms = pssms
        self.species = species
        self.miRNAs = self.setMiRNAs(0,8,minor,p5,p3)
        # Trim sequences down
        self.miRNAs_6mer_1 = self.trimSeqs(deepcopy(self.miRNAs),0,6)
        self.miRNAs_6mer_2 = self.trimSeqs(deepcopy(self.miRNAs),1,7)
        self.miRNAs_6mer_3 = self.trimSeqs(deepcopy(self.miRNAs),2,8)
        self.miRNAs_7mer_m8 = self.trimSeqs(deepcopy(self.miRNAs),1,8)
        self.miRNAs_7mer_a1 = self.trimSeqs(deepcopy(self.miRNAs),0,7)
        self.miRNAs_8mer = self.trimSeqs(deepcopy(self.miRNAs),0,8)
        dirName = 'miRNA'
        if not os.path.exists(dirName):
            os.mkdir(dirName) 
        if 6 in seedModel:
            self.permKMers_6mer = self.allKmers(6)
           
        if 7 in seedModel:
            self.permKMers_7mer = self.allKmers(7)
            
        if 8 in seedModel:
            self.permKMers_8mer = self.allKmers(8)
            
        miRNAScores = {}
        cur = 1
        # Building HMM Model
        for pssm in pssms:
            print 'Building HMM model for '+str(pssm.getConsensusMotif())+'...'
            miRNAScores[pssm.getName()] = []
            # Then setup the HMM
            ## States ##
            ## and Starting Probabilities ##
            # NM1 = no match 1
            # NM2 = no match 2
            # PSSMi = PSSM at spot i
            maxPSSMi = len(pssm.getMatrix())
            states = ['NM1', 'NM2']
            sp = {'NM1': float(1)/float(maxPSSMi+1), 'NM2': 0}
            # Add the PSSM states
            for i in range(maxPSSMi):
                states += ['PSSM'+str(i)]
                sp['PSSM'+str(i)] = float(1)/float(maxPSSMi+1)
                if wobble==True:
                    states += ['WOBBLE'+str(i)]
                    sp['WOBBLE'+str(i)] = 0
            ## Transition probabilities
            tp = {}
            # NM1
            nm1_2_nm1 = 0.01
            tp['NM1'] = { 'NM1': nm1_2_nm1, 'NM2': 0 }
            leftOver1 = float(1-nm1_2_nm1)/float(maxPSSMi)
            for i in range(maxPSSMi):
                tp['NM1']['PSSM'+str(i)] = leftOver1
                if wobble==True:
                    tp['NM1']['WOBBLE'+str(i)] = 0 # Don't start a seed with a wobble
            # NM2
            tp['NM2'] = { 'NM1': 0, 'NM2': 1 }
            for i in range(maxPSSMi):
                tp['NM2']['PSSM'+str(i)] = 0
                if wobble==True:
                    tp['NM2']['WOBBLE'+str(i)] = 0
            # PSSMis
            for i in range(maxPSSMi):
                tp['PSSM'+str(i)] = { 'NM1': 0, 'NM2': 0.01 }
                if wobble==True:
                    tp['WOBBLE'+str(i)] = { 'NM1': 0, 'NM2': 0.01 }
                if i==(maxPSSMi-1):
                    tp['PSSM'+str(i)]['NM2'] = 1
                    if wobble==True:
                        tp['WOBBLE'+str(i)]['NM2'] = 1
                for j in range(maxPSSMi):
                    if j == i+1:
                        if wobble==True:
                            # Allow wobbly matches if T is >= wobbleCut
                            if float(pssm.getMatrix()[i+1][2])>=float(wobbleCut) or float(pssm.getMatrix()[i+1][3])>=float(wobbleCut):
                                tp['PSSM'+str(i)]['PSSM'+str(j)] = 0.80
                                tp['PSSM'+str(i)]['WOBBLE'+str(j)] = 0.19
                            # Otherwise don't allow wobbly matches
                            else:
                                tp['PSSM'+str(i)]['PSSM'+str(j)] = 0.99
                                tp['PSSM'+str(i)]['WOBBLE'+str(j)] = 0
                            tp['WOBBLE'+str(i)]['PSSM'+str(j)] = 1
                            tp['WOBBLE'+str(i)]['WOBBLE'+str(j)] = 0
                        else:
                            tp['PSSM'+str(i)]['PSSM'+str(j)] = 0.99
                    else:
                        tp['PSSM'+str(i)]['PSSM'+str(j)] = 0
                        if wobble==True:
                            tp['PSSM'+str(i)]['WOBBLE'+str(j)] = 0
                            tp['WOBBLE'+str(i)]['PSSM'+str(j)] = 0
                            tp['WOBBLE'+str(i)]['WOBBLE'+str(j)] = 0
            ## Emission probabilities
            ep = {}
            # NM1
            ep['NM1'] = { 'A': 0.25, 'C': 0.25, 'G': 0.25, 'T': 0.25 }
            # S1 - None
            # S2 - None
            # NM2
            ep['NM2'] = { 'A': 0.25, 'C': 0.25, 'G': 0.25, 'T': 0.25 }
            # PSSMis
            for i in range(maxPSSMi):
                ep['PSSM'+str(i)] = { 'A': pssm.getMatrix()[i][0], 'C': pssm.getMatrix()[i][1], 'G': pssm.getMatrix()[i][2], 'T': pssm.getMatrix()[i][3] }
                # If motif has both G and U probability greater than wobblecut or random (0.25)
                if wobble==True:
                    if float(pssm.getMatrix()[i][2])>=float(wobbleCut) and float(pssm.getMatrix()[i][3])>=float(wobbleCut):
                        ep['WOBBLE'+str(i)] = { 'A': 0.5, 'C': 0.5, 'G': 0, 'T': 0 }
                    # If motif has G greater than wobblecut or random (0.25)
                    elif float(pssm.getMatrix()[i][2])>=float(wobbleCut):
                        ep['WOBBLE'+str(i)] = { 'A': 1, 'C': 0, 'G': 0, 'T': 0 }
                    # If motif has U greater than wobblecut or random (0.25)
                    elif float(pssm.getMatrix()[i][3])>=float(wobbleCut):                
                        ep['WOBBLE'+str(i)] = { 'A': 0, 'C': 1, 'G': 0, 'T': 0 }
                    # Otherwise be random (0.25 x 4)
                    else:
                        ep['WOBBLE'+str(i)] = { 'A': 0.25, 'C': 0.25, 'G': 0.25, 'T': 0.25 }
            print 'Done.\n'
            # Calculate the distribution of p-values for the PSSM
            if 6 in seedModel:
                print 'Computing background distribution for 6mer ('+str(len(self.permKMers_6mer))+')...'
                totPs_6mer = []
                vitPs_6mer = []
                for kMer in self.permKMers_6mer:
                    permVit = self.forwardViterbi(list(kMer), states, sp, tp, ep)
                    totPs_6mer.append(permVit[0])
                    vitPs_6mer.append(permVit[2])
                self.totPs_6mer = totPs_6mer
                self.vitPs_6mer = vitPs_6mer
            if 7 in seedModel and len(pssm.getMatrix())>=7:
                print 'Computing background distribution for 7mer ('+str(len(self.permKMers_7mer))+')...'
                totPs_7mer = []
                vitPs_7mer = []
                for kMer in self.permKMers_7mer:
                    permVit = self.forwardViterbi(list(kMer), states, sp, tp, ep)
                    totPs_7mer.append(permVit[0])
                    vitPs_7mer.append(permVit[2])
                self.totPs_7mer = totPs_7mer
                self.vitPs_7mer = vitPs_7mer
            if 8 in seedModel and len(pssm.getMatrix())>=8:
                print 'Computing background distribution for 8mer ('+str(len(self.permKMers_8mer))+')...'
                totPs_8mer = []
                vitPs_8mer = []
                for kMer in self.permKMers_8mer:
                    permVit = self.forwardViterbi(list(kMer), states, sp, tp, ep)
                    totPs_8mer.append(permVit[0])
                    vitPs_8mer.append(permVit[2])
                self.totPs_8mer = totPs_8mer
                self.vitPs_8mer = vitPs_8mer
            print 'Done.\n'
            ## Do viterbi for each miRNA and store data
            print 'Starting miRNA detection for '+str(pssm.getConsensusMotif())+':'
            if textOut==True:
                writeMeOut = {}
                dirName = 'miRNA'
                if not os.path.exists(dirName):
                    os.mkdir(dirName) 
                outFile = open(dirName+'/'+slugify(str(pssm.getName()))+'.csv','w')
                outFile.write('miRNAname,miRNAseed,AlignStart,AlignStop,AlignLength,AlignmentModel,MotifAlign (5\'->3\'),Align,SeedAlign(3\'->5\'),P(Total),P-valueTotal,P(Viterbi),P-valueViterbi') # Header
                #out2File = open(dirName+'/'+str(pssm.getName())+'_all.csv','w')
                headNum = 0
                if 6 in seedModel:
                    headNum += 3
                if 7 in seedModel and len(pssm.getMatrix())>=7:
                    headNum += 2
                if 8 in seedModel and len(pssm.getMatrix())>=8:
                    headNum += 1
                #out2File.write(','.join(['miRNAname,miRNAseed,AlignStart,AlignStop,AlignLength,AlignmentModel,MotifAlign (5\'->3\'),Align,SeedAlign(3\'->5\'),P(Total),P-valueTotal,P(Viterbi),P-valueViterbi']*headNum)) # header
            for miRNA in self.miRNAs_6mer_1:
                # Now decide which complementary seed is the best fit for each miRNA (take the max vitP)
                forVit = None
                compModel = None
                seed = None
                tmpPs = None
                writeMe = ''
                if 6 in seedModel:
                    # Compute probabilities
                    forVit_6mer_1 = self.forwardViterbi(list(self.miRNAs_6mer_1[miRNA]), states, sp, tp, ep)
                    forVit_6mer_2 = self.forwardViterbi(list(self.miRNAs_6mer_2[miRNA]), states, sp, tp, ep)
                    forVit_6mer_3 = self.forwardViterbi(list(self.miRNAs_6mer_3[miRNA]), states, sp, tp, ep)
                    if textOut==True:
                        writeMe += ','.join(self.outData([pssm, pssm.getConsensusMotif(), miRNA, self.reverseComplement(self.miRNAs_6mer_1[miRNA]), deepcopy(forVit_6mer_1)], self.getPValue(forVit_6mer_1[0],totPs_6mer), self.getPValue(forVit_6mer_1[2],vitPs_6mer), '6mer_1', self.miRNAs_8mer[miRNA]))
                        writeMe += ','+','.join(self.outData([pssm, pssm.getConsensusMotif(), miRNA, self.reverseComplement(self.miRNAs_6mer_2[miRNA]), deepcopy(forVit_6mer_2)], self.getPValue(forVit_6mer_2[0],totPs_6mer), self.getPValue(forVit_6mer_2[2],vitPs_6mer), '6mer_2', self.miRNAs_8mer[miRNA]))
                        writeMe += ','+','.join(self.outData([pssm, pssm.getConsensusMotif(), miRNA, self.reverseComplement(self.miRNAs_6mer_3[miRNA]), deepcopy(forVit_6mer_3)], self.getPValue(forVit_6mer_3[0],totPs_6mer), self.getPValue(forVit_6mer_3[2],vitPs_6mer), '6mer_3', self.miRNAs_8mer[miRNA]))
                    # Default set 6mer_1 as the best
                    forVit = forVit_6mer_1
                    compModel = '6mer_1'
                    seed = self.miRNAs_6mer_1[miRNA]
                    tmpPs = [totPs_6mer,vitPs_6mer]
                    # See if the others are better
                    if self.getPValue(forVit_6mer_2[2],vitPs_6mer) <= self.getPValue(forVit[2],tmpPs[1]):
                        forVit = forVit_6mer_2
                        compModel = '6mer_2'
                        seed = self.miRNAs_6mer_2[miRNA]
                        tmpPs = [totPs_6mer,vitPs_6mer]
                    if self.getPValue(forVit_6mer_3[2],vitPs_6mer) <= self.getPValue(forVit[2],tmpPs[1]):
                        forVit = forVit_6mer_3
                        compModel = '6mer_3'
                        seed = self.miRNAs_6mer_3[miRNA]
                        tmpPs = [totPs_6mer,vitPs_6mer]
                if 7 in seedModel and len(pssm.getMatrix())>=7:
                    # Compute probabilities
                    forVit_7mer_m8 = self.forwardViterbi(list(self.miRNAs_7mer_m8[miRNA]), states, sp, tp, ep)
                    forVit_7mer_a1 = self.forwardViterbi(list(self.miRNAs_7mer_a1[miRNA]), states, sp, tp, ep)
                    if textOut==True:
                        if 6 in seedModel:
                            writeMe += ','
                        writeMe += ','.join(self.outData([pssm, pssm.getConsensusMotif(), miRNA, self.reverseComplement(self.miRNAs_7mer_m8[miRNA]), deepcopy(forVit_7mer_m8)], self.getPValue(forVit_7mer_m8[0],totPs_7mer), self.getPValue(forVit_7mer_m8[2],vitPs_7mer), '7mer_m8', self.miRNAs_8mer[miRNA]))
                        writeMe += ',' + ','.join(self.outData([pssm, pssm.getConsensusMotif(), miRNA, self.reverseComplement(self.miRNAs_7mer_a1[miRNA]), deepcopy(forVit_7mer_a1)], self.getPValue(forVit_7mer_a1[0],totPs_7mer), self.getPValue(forVit_7mer_a1[2],vitPs_7mer), '7mer_a1', self.miRNAs_8mer[miRNA]))
                    # If not yet set then default it
                    if forVit==None:
                        forVit = forVit_7mer_m8
                        compModel = '7mer_m8'
                        seed = self.miRNAs_7mer_m8[miRNA]
                        tmpPs = [totPs_7mer,vitPs_7mer]
                    # Or see if it is better
                    elif self.getPValue(forVit_7mer_m8[2],vitPs_7mer) <= self.getPValue(forVit[2],tmpPs[1]):
                        forVit = forVit_7mer_m8
                        compModel = '7mer-m8'
                        seed = self.miRNAs_7mer_m8[miRNA]
                        tmpPs = [totPs_7mer,vitPs_7mer]
                    # See if they are better
                    if self.getPValue(forVit_7mer_a1[2],vitPs_7mer) <= self.getPValue(forVit[2],tmpPs[1]):
                        forVit = forVit_7mer_a1
                        compModel = '7mer-a1'
                        seed = self.miRNAs_7mer_a1[miRNA]
                        tmpPs = [totPs_7mer,vitPs_7mer]
                if 8 in seedModel and len(pssm.getMatrix())>=8:
                    # Compute probabilities
                    forVit_8mer = self.forwardViterbi(list(self.miRNAs_8mer[miRNA]), states, sp, tp, ep)
                    if textOut==True:
                        if 6 in seedModel or 7 in seedModel:
                            writeMe += ','
                        writeMe += ','.join(self.outData([pssm, pssm.getConsensusMotif(), miRNA, self.reverseComplement(self.miRNAs_8mer[miRNA]), deepcopy(forVit_8mer)], self.getPValue(forVit_8mer[0],totPs_8mer), self.getPValue(forVit_8mer[2],vitPs_8mer), '8mer', self.miRNAs_8mer[miRNA]))
                    # If not yet set then default it
                    if forVit==None:
                        forVit = forVit_8mer
                        compModel = '8mer'
                        seed = self.miRNAs_8mer[miRNA]
                        tmpPs = [totPs_8mer,vitPs_8mer]
                    # Or see if it is better
                    elif self.getPValue(forVit_8mer[2],vitPs_8mer) <= self.getPValue(forVit[2],tmpPs[1]):
                        forVit = forVit_8mer
                        compModel = '8mer'
                        seed = self.miRNAs_8mer[miRNA]
                        tmpPs = [totPs_8mer,vitPs_8mer]
                # PSSM.name, PSSM.consesusMotif, miRNA.name, miRNA.seed, state.path, totP, totPValue, vitP, vitPValue
                newScore = {'miRNA.name':miRNA, 'miRNA.seed':seed, 'statePath':deepcopy(forVit[1]), 'totP':forVit[0], 'totPValue':self.getPValue(forVit[0],tmpPs[0]), 'vitP':forVit[2], 'vitPValue':self.getPValue(forVit[2],tmpPs[1]), 'model':compModel}
                miRNAScores[pssm.getName()] = self.addSorted(miRNAScores[pssm.getName()],newScore)
                if textOut==True:
                    #out2File.write('\n'+writeMe)
                    writeMeOut[miRNA] = ','.join(self.outData([pssm, pssm.getConsensusMotif(), miRNA, self.reverseComplement(seed), forVit], self.getPValue(forVit[0],tmpPs[0]), self.getPValue(forVit[2],tmpPs[1]), compModel, self.miRNAs_8mer[miRNA]))
            
            if textOut==True:
                outFile.write('\n'+'\n'.join([writeMeOut[i['miRNA.name']] for i in miRNAScores[pssm.getName()]]))
                outFile.close()
                #out2File.close()
            #if cur%10==0:
            #    stdout.write(str(cur))
            #else:
            #    stdout.write('.')
            #stdout.flush()
            print 'Done.\n'
            cur += 1
        print 'miRvestigator analysis completed.\n'
        self.miRNAScores = miRNAScores

    def getScore(self, forVit, vitPs):
        return (float(forVit[0])/float(forVit[2]))*float(self.getPValue(forVit[2],vitPs))

    # Generates all possible sequences with letters to the length of depth.
    def allKmers(self,depth,letters=['A','C','G','T'],seqs=[''],curdepth=0):
        newseqs = []
        for seq in seqs:
            for letter in letters:
                newseqs.append(seq + letter)
        if depth > curdepth:
            return(self.allKmers(depth,letters,newseqs,curdepth + 1))
        else:
            return(seqs)
    
    # Get the miRNAs to compare against
    def setMiRNAs(self,seedStart,seedEnd, minor=True, p5=True, p3=True):
        if not os.path.exists('mature.fa.gz'):
            print '\nDownloading miRNA seeds from miRBase.org...'
            # Grab down the latest miRNA data from mirbase.org:
            #  ftp://mirbase.org/pub/mirbase/CURRENT/mature.fa.gz
            from ftplib import FTP
            ftp1 = FTP('mirbase.org')
            ftp1.login()
            ftp1.cwd('/pub/mirbase/CURRENT/')
            # Get the miRBase.org version number for reference.
            self.miRNAver = (ftp1.pwd().split('/'))[-1]
            outFile = open('mature.fa.gz','wb')
            ftp1.retrbinary('RETR mature.fa.gz',outFile.write)
            outFile.close()
            ftp1.quit()
            print 'Done.\n'
        else:
            print '\nUsing already downloaded miRNA seeds.\n'

        # Read in miRNAs: miRNAs are labeled by the hsa-* names and grabbing 2-8bp
        ### Could merge these as they come in so that don't do redundant, and also so that the labels are together
        import gzip
        miRNAFile = gzip.open('mature.fa.gz','r')
        miRNAs = {}
        while 1:
            miRNALine = miRNAFile.readline()
            seqLine = miRNAFile.readline()
            if not miRNALine:
                break
            # Get the miRNA name
            curMiRNA = (miRNALine.lstrip('>').split(' '))[0]
            if (curMiRNA.split('-'))[0]==self.species:
                if (minor==True or curMiRNA.find('*')==-1) and (p5==True or curMiRNA.find('-5p')==-1) and (p3==True or curMiRNA.find('-3p')==-1):
                    # Now grab out the 2-8bp and do reverse complement on it
                    miRNAs[curMiRNA] = self.reverseComplement((seqLine.strip())[seedStart:seedEnd])
        miRNAFile.close()
        
        # How many distinct kMers in miRNAs
        miRNAuniq = {}
        for miRNA in miRNAs:
            if not miRNAs[miRNA] in miRNAuniq:
                miRNAuniq[miRNAs[miRNA]] = [miRNA]
            else:
                miRNAuniq[miRNAs[miRNA]].append(miRNA)
        # Then merge them
        miRNAsMerged = {}
        for seed in miRNAuniq:
            tmpName = '_'.join(miRNAuniq[seed])
            miRNAsMerged[tmpName] = seed
        return miRNAsMerged

    def trimSeqs(self, miRNAs, start, stop):
        tmp = {}
        for miRNA in miRNAs:
            tmp[miRNA] = miRNAs[miRNA][start:stop]
            #print tmp[miRNA]
        return tmp
        
    # Complement
    def complement(self,seq):
        complement = {'A':'T', 'T':'A', 'C':'G', 'G':'C', 'N':'N', 'U':'A'}
        complseq = [complement[base] for base in seq]
        return complseq

    # Reverse complement
    def reverseComplement(self,seq):
        seq = list(seq)
        seq.reverse()
        return ''.join(self.complement(seq))

    # Reverse complement
    def reverseMe(self,seq):
        seq = list(seq)
        seq.reverse()
        return ''.join(seq)

    # Modified from From wikipedia to do both forward calculation and viterbi
    def forwardViterbi(self, obs, states, start_p, trans_p, emit_p):
       T = {}
       for state in states:
           ##          prob.           V. path  V. prob.
           T[state] = (start_p[state], [state], start_p[state])
       for output in obs:
           U = {}
           for next_state in states:
               total = float(0)
               argmax = None
               valmax = float(0)
               for source_state in states:
                   (prob, v_path, v_prob) = T[source_state]
                   p = emit_p[source_state][output] * trans_p[source_state][next_state]
                   prob *= p
                   v_prob *= p
                   total += prob
                   if v_prob > valmax:
                       argmax = v_path + [next_state]
                       valmax = v_prob
               U[next_state] = (total, argmax, valmax)
           T = U
       ## apply sum/max to the final states:
       total = float(0)
       argmax = None
       valmax = float(0)
       for state in states:
           (prob, v_path, v_prob) = T[state]
           total += prob
           if v_prob > valmax:
               argmax = v_path
               valmax = v_prob
       return (total, argmax, valmax)

    # Decide whether to add and add at correct position
    # Strucuture of elements:
    # [pssm, getConsensus(pssms[pssm]), miRNA, miRNAs[miRNA], forVit]
    def addSorted(self,all,new):
        inserted = 0
        if len(all)>0:
            for i in range(len(all)):
                if new['vitPValue']<all[i]['vitPValue']:
                    all.insert(i,new)
                    inserted = 1
                    break
            if inserted==0:
                all.append(new)
        else:
            all.append(new)
        return all

    # Get p-value from a probability and a distribution
    def getPValue(self,prob,dist):
        a = float(len([i for i in dist if i>=prob]))
        b = float(len(dist))
        if not a==0:
            return a/b
        else:
            return 0

    # Get score list for a PSSM
    def getScoreList(self,pssmName):
        return self.miRNAScores[pssmName]

    # Get top hit(s) for a PSSM.
    # Returns either one or more miRNAs based on whether a clear winner or a tie.
    def getTopHit(self,pssmName):
        scoreList = self.getScoreList(pssmName)
        if scoreList[0]['vitPValue']<scoreList[1]['vitPValue']:
            return [scoreList[0]]
        else:
            retMe = []
            i = 0
            while scoreList[0]['vitPValue']==scoreList[i]['vitPValue']:
                retMe.append(scoreList[i])
                i += 1
            return retMe

    # Get the scores for a PSSM.
    # Returns all miRNAs which conatin the miRNA name.
    def getmiRNAHit(self,pssmName,miRNAname):
        scoreList = self.getScoreList(pssmName)
        retMe = []
        for i in range(len(scoreList)):
            if not scoreList[i]['miRNA.name'].find(miRNAname)==-1:
                scoreList[i]['rank'] = i
                retMe.append(scoreList[i])
        return retMe
    
    # Strucuture of elements:
    # [pssm, getConsensus(pssms[pssm]), miRNA, miRNAs[miRNA], forVit]
    # <tr><td>miRNA Name</td><td>Alignment Start<sup>*</sup></td><td>Alignment Stop<sup>*</sup></td><td>Alignment Length</td><td>Motif (Length)</td><td>Alignment Type</td><td>Alignment</td><td>P(Alignment)</td></tr>
    def outHtml(self, outMe):
        writeMe = ''
        # miRNA name
        writeMe += '<tr align=\'center\' valign=\'center\'><td>'+str(outMe[2])+'</td><td>'+str(outMe[3])+'</td>'
        alignment = outMe[4][1] # Grab the alignment
        alignment.pop() # Get rid of the extra state which is added by the forwardViterbi function
        start = 1
        if alignment[0]=='NM1':
            for i in alignment:
                if i=='NM1':
                    start += 1
        # Alignment
        seedAlign = ''
        seed = list(outMe[3])
        motifAlign = ''
        motif = list(outMe[1])
        alignMe = alignment
        aligned = ''
        lenMatch = 0
        # First get them zero'd to the same point
        if start>1:
            for i in range(start-1):
                seedAlign += seed.pop(0)
                aligned += ' '
                motifAlign += '-'
                alignMe.pop(0)
        if not alignMe[0]=='PSSM0' and not alignMe[0]=='WOBBLE0':
            for i in range(int(alignMe[0][4])):
                seedAlign += '-'
                aligned += ' '
                motifAlign += motif.pop(0)
        # Then add the parts that align
        while 1:
            if len(alignMe)==0 or alignMe[0]=='NM2':
                break
            seedAlign += seed.pop(0)
            if alignMe[0][0]=='P':
                aligned += '|'
            elif alignMe[0][0]=='W':
                aligned += ':'
            lenMatch += 1
            motifAlign += motif.pop(0)
            alignMe.pop(0)
        # Then do the ending
        if len(alignMe)>0:
            for i in alignMe:
                seedAlign += seed[0]
                seed = seed[1:]
                aligned += ' '
                motifAlign += '-'
            alignMe = []
        if len(motif)>0 and len(alignMe)==0:
            for i in motif:
                seedAlign += '-'
                aligned += ' '
                motifAlign += i
        writeMe += '<td>'+str(start)+'</td><td>'+str(start+lenMatch-1)+'</td><td>'+str(lenMatch)+'</td><td><font face="Courier New"><pre>Seed  '+str(seedAlign)+'\n      '+str(aligned)+'\nMotif '+str(motifAlign)+'</pre></font></td>'
        # P(Alignment)
        writeMe += '<td>'+str(outMe[4][0])+'</td><td>'+str(float(len([i for i in self.totPs if i>=outMe[4][0]]))/float(len(self.totPs)))+'</td><td>'+str(outMe[4][2])+'</td><td>'+str(float(len([i for i in self.vitPs if i>=outMe[4][2]]))/float(len(self.vitPs)))+'</td></tr>'
        
        return writeMe
    
    # Decide whether to add and add at correct position
    # Strucuture of elements:
    # input = [pssm, getConsensus(pssms[pssm]), miRNA, miRNAs[miRNA], forVit], totPs, vitPs (Ps are permuted probabilities)
    # output = [miRNAname,miRNAseed,AlignStart,AlignStop,AlignLength,SeedAlign,Align,MotifAlign,P(Total),P-valueTotal,P(Viterbi),P-valueViterbi]
    def outData(self,outMe,totP,vitP,compModel,fullSeed):
        #print outMe[4][1]
        output = []
        # miRNA name
        output += [outMe[2],self.reverseComplement(fullSeed)]
        alignment = outMe[4][1] # Grab the alignment
        alignment.pop() # Get rid of the extra state which is added by the forwardViterbi function
        start = 1
        if alignment[0]=='NM1':
            for i in alignment:
                if i=='NM1':
                    start += 1
        # Alignment
        seedAlign = ''
        seed = list(self.reverseMe(outMe[3]))
        motifAlign = ''
        motif = list(outMe[1])
        alignMe = alignment
        aligned = ''
        lenMatch = 0
        # First get them zero'd to the same point
        if start>1:
            for i in range(start-1):
                seedAlign += seed.pop(0)
                aligned += '_'
                motifAlign += '-'
                alignMe.pop(0)
        if len(alignMe)>0 and not alignMe[0]=='PSSM0' and not alignMe[0]=='WOBBLE0':
            if alignMe[0][0]=='P':
                upTo = int(alignMe[0][4])
            elif alignMe[0][0]=='W':
                upTo = int(alignMe[0][6])
            for i in range(upTo):
                seedAlign += '-'
                aligned += '_'
                motifAlign += motif.pop(0)
        # Then add the parts that align
        while 1:
            if len(alignMe)==0 or alignMe[0]=='NM2':
                break
            seedAlign += seed.pop(0)
            if alignMe[0][0]=='P':
                aligned += '|'
            elif alignMe[0][0]=='W':
                aligned += ':'
            lenMatch += 1
            motifAlign += motif.pop(0)
            alignMe.pop(0)
        # Then do the ending
        if len(alignMe)>0:
            for i in alignMe:
                seedAlign += seed[0]
                seed = seed[1:]
                aligned += '_'
                motifAlign += '-'
            alignMe = []
        if len(motif)>0 and len(alignMe)==0:
            for i in motif:
                seedAlign += '-'
                aligned += '_'
                motifAlign += i
        output += [start,start+lenMatch-1,lenMatch,compModel,"'"+motifAlign,"'"+aligned,"'"+seedAlign]
        # P(Alignment)
        output += [outMe[4][0],totP,outMe[4][2],vitP]
        return [str(i) for i in output]

# A class designed to hold a position specific scoring matrix
# and be able to output this in many different formats
#
# Variables:
# pssmName - name
# eValue - the significance of the motif
# nsites - number of genes that have the motif
# genes - the genes that have the motif
# pssmMatrix - a matrix of x by 4 [A, C, G, T]
#
# Functions:
# readPssm(pssmFileName) - Reads in the pssm from the specified file, file name should be as absolute as necessary.
# getMatrix() - returns the pssm matrix as is
# getMemeFormatted() - returns the pssm matrix as a meme 3 formatted string
# colConsensus() - gets the consensus letter for a column of the pssm matrix
# getConsensusMotif() - repeatedly calls colConsensus to get the complete consensus motif
# getName() - return the name of the pssm "bicluster#_motif#<optional _3pUTR>"
# getNSites() - return the number of genes with the motif
# getEValue() - return the significance of the motif for the bicluster
# getGenes() - return the names of the genes that have the motif
#
class pssm:
    # Initialize the pssm
    def __init__(self, pssmFileName=None, biclusterName=None, nsites=None, eValue=None, pssm=None, genes=None):
        if not pssmFileName==None:
            self.name = str(biclusterName)+'_'+(((pssmFileName.split('.'))[0]).split('/'))[-1]
            self.readPssm(pssmFileName)
        else:
            self.name = biclusterName
            self.nsites = nsites
            self.eValue = eValue
            self.matrix = pssm
            self.genes = genes

    # Read in the PSSM matrix
    def readPssm(self, pssmFileName):
        pssmFile = open(pssmFileName,'r')
        firstLine = pssmFile.readline().strip().split(',')
        self.eValue = firstLine[0]
        self.nsites = firstLine[1]
        self.genes = []
        for i in range(int(self.nsites)):
            self.genes.append(pssmFile.readline().strip().split(',')[0])
        self.matrix = []
        self.matrix += [[float(i) for i in line.strip().split(',')] for line in pssmFile.readlines() if line]
        pssmFile.close()

    # Returns the name of the PSSM
    def getName(self):
        return deepcopy(self.name)

    # Sets the name of the PSSM
    def setName(self,name):
        self.name = name

    # Returns the E-value of the PSSM
    def getEValue(self):
        return deepcopy(self.eValue)

    # Returns the number of sites for the PSSM
    def getNSites(self):
        return deepcopy(self.nsites)

    # Returns the number of genes of the PSSM
    def getNumGenes(self):
        return len(self.genes)

    # Returns the genes of the PSSM
    def getGenes(self):
        return deepcopy(self.genes)

    # Returns the matrix
    def getMatrix(self):
        return self.matrix

    # Pads the meme nucleotide frequencies with zeros
    def padMe(self,str1):
        if len(str1)<8:
            for i in range(8-len(str1)):
                str1 += '0'
        return str1

    # Retunrs a log-odds value
    def logOdds(self, p, f):
        p = float(p)
        f = float(f)
        if p==float(0):
            v1 = str(int(round(log(float(1E-300)/f,2),0)))
        else:
            v1 = str(int(round(log(p/f,2),0)))
        if len(v1)<6:
            for i in range(6-len(v1)):
                v1 = ' ' + v1
        return v1

    # Returns a meme 3 formatted string (letter-probability matrix)
    def getMemeFormatted(self,atFreq=0.25,cgFreq=0.25):
        memeFormatted = 'MOTIF '+self.name+'\n'
        memeFormatted += 'BL   MOTIF '+self.name+' width=0 seqs=0\n'
        memeFormatted += 'letter-probability matrix: alength= 4 w= '+str(len(self.matrix))+' nsites= '+self.nsites+' E= '+self.eValue
        for i in self.matrix:
            memeFormatted += '\n '+self.padMe(str(round(float(i[0]),6)))+'  '+self.padMe(str(round(float(i[1]),6)))+'  '+self.padMe(str(round(float(i[2]),6)))+'  '+self.padMe(str(round(float(i[3]),6)))
        return memeFormatted

    # Returns a mast formatted string (log-odds matrix)
    def getMastFormatted(self,atFreq=0.25,cgFreq=0.25):
        mastFormatted = 'log-odds matrix: alength= 4 w= '+str(len(self.matrix))
        for i in self.matrix:
            mastFormatted += '\n '+self.logOdds(i[0],atFreq)+'  '+self.logOdds(i[1],cgFreq)+'  '+self.logOdds(i[2],cgFreq)+'  '+self.logOdds(i[3],atFreq)
        return mastFormatted

   # Returns the consensus word for a motif
    def getConsensusMotif(self, lim1=0.6, lim2=0.8, three=0):
        consensus = ''
        for i in range(len(self.matrix)):
            consensus += self.colConsensus(self.matrix, i, lim1, lim2, three)
        return consensus

    # Returns the consensus letter for a motif column
    def colConsensus(self, pssm, i, lim1, lim2, three):
        two_base_l = ['Y','R','W','S','K','M']
        three_base_l = ['V','H','D','B']
        conLet = 'N'
        if float(pssm[i][0])>=lim1:
            conLet = 'A'
        elif float(pssm[i][1])>=lim1:
            conLet = 'C'
        elif float(pssm[i][2])>=lim1:
            conLet = 'G'
        elif float(pssm[i][3])>=lim1:
            conLet = 'T'
        else:
            two_base_c = [float(pssm[i][1])+float(pssm[i][3]), float(pssm[i][0])+float(pssm[i][2]), float(pssm[i][0])+float(pssm[i][3]), float(pssm[i][1])+float(pssm[i][2]), float(pssm[i][2])+float(pssm[i][3]), float(pssm[i][0])+float(pssm[i][1])]
            three_base_c = [float(pssm[i][0])+float(pssm[i][1])+float(pssm[i][2]), float(pssm[i][0])+float(pssm[i][1])+float(pssm[i][3]), float(pssm[i][0])+float(pssm[i][2])+float(pssm[i][3]), float(pssm[i][1])+float(pssm[i][2])+float(pssm[i][3])]
            pMax = 0
            for k in range(0,6):
                if two_base_c[k] > pMax:
                    pMax = two_base_c[k]
                    conLet = two_base_l[k]
            if not pMax>lim2 and three==1:
                for k in range(0,4):
                    if three_base_c[k] > pMax:
                        pMax = three_base_c[k]
                        conLet = three_base_l[k]
            if not pMax>lim2:
                conLet = 'N'
        return conLet



# Code to allow command line running of script
from optparse import OptionParser

print "###############################################################"
print "#                                                             #"
print "# miRvestigator Stand Alone Application (Python)              #"
print "# developed by Chris Plaisier (cplaisier@systemsbiology.org)  #"
print "# Licensed under the Academic Free License version 2.1        #"
print "#                                                             #"
print "###############################################################"

#### Option Parsing ####
usage = "python %prog -p example.fasta -s hsa -wobble NA -6 N -7 N -8 Y"
parser = OptionParser(usage)
parser.add_option("-p", "--pssmFile", action="store", type="string", dest="pssmFile", default="NA", help="[Required] Name of the PSSM file entered using a fasta like format where each motif is named and is followed with rows A, C, G, T and columns equal to the lenght of the motif (values in the matrix should be separated by spaces). The values entered should be probabilities and the columns should sum to 1.")
parser.add_option("-s", "--species", action="store", type="string", dest="species", default="hsa", help="Species code whose miRNAs the PSSMs should be compared against. Common species codes (<code> = <species>): cel = Caenohabditis elegans (worm), dme = Drosophila melanogaster (fly), gga = Gallus gallus (chicken), hsa = Homo sapiens (human), mmu = Mus musculus (mice), rno = Rattus norvegicus (rat). Defaults to hsa, human.")
parser.add_option("-w", "--wobble", action="store", type="string", dest="wobble", default="NA", help="Whether wobble base-pairing should be modeled. Set to minimum frequency of G or U (default is 0.25).")
parser.add_option("-6", "--6mer", action="store", type="string", dest="m6", default="Y", help="Whether 6mer seed model should be included. (Y or N). Defaults to Y.")
parser.add_option("-7", "--7mer", action="store", type="string", dest="m7", default="Y", help="Whether 7mer seed model should be included. (Y or N). Defaults to Y.")
parser.add_option("-8", "--8mer", action="store", type="string", dest="m8", default="Y", help="Whether 8mer seed model should be included. (Y or N). Defaults to Y.")
(options, args) = parser.parse_args()

if options.pssmFile=='NA':
    parser.print_help()
    sys.exit(0)

wobble = False
wobbleCut = 0.25
if not options.wobble=='NA':
    wobble = True
    wobbleCut = float(options.wobble)

seedModels = []
if options.m6=='Y':
    seedModels.append(6)
if options.m7=='Y':
    seedModels.append(7)
if options.m8=='Y':
    seedModels.append(8)

# 1. Read in PSSMs from file
print '\nReading in pssms...'
inFile = open(options.pssmFile,'r')
pssms = []
while 1:
    line = inFile.readline()
    if not line:
        break
    if line[0]=='>':
        name = line.strip().lstrip('>')
        aVals = inFile.readline().strip().split(' ')
        cVals = inFile.readline().strip().split(' ')
        gVals = inFile.readline().strip().split(' ')
        tVals = inFile.readline().strip().split(' ')
        matrix = []
        for i in range(len(aVals)):
            matrix.append([float(aVals[i]),float(cVals[i]),float(gVals[i]),float(tVals[i])])
        pssms.append(pssm(biclusterName=name, nsites='NA', eValue='NA', pssm=matrix,genes=''))
inFile.close()
print 'Read',len(pssms),'pssms.'

# 2. Compare to miRDB using miRvestigator
print '\nRunning miRvestigator...'
mV = miRvestigator(pssms,seedModel=seedModels,minor=True,p5=True,p3=True,wobble=wobble,wobbleCut=wobbleCut,species=options.species)
print 'Done.'

print '\nResults can be found in the miRNA sub-directory.'

