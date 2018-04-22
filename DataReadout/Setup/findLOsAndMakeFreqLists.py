import numpy as np
import matplotlib.pyplot as plt
import pdb
from createTemplarResList import createTemplarResList

def findLOs(freqs, loRange=0.2, nIters=10000, colParamWeight=1, resBW=0.0002):
    '''
    Finds the optimal LO frequencies for a feedline, given a list of resonator frequencies.
    Does Monte Carlo optimization to minimize the number of out of band tones and sideband 
    collisions.
    
    Parameters
    ----------
        freqs - list of resonator frequencies, in GHz
        loRange - size of LO search band, in GHz
        nIters - number of optimization interations
        colParamWeight - relative weighting between number of collisions and number of omitted
            tones in cost function. 1 usually gives good performance, set to 0 if you don't want
            to optimize for sideband collisions. 
        resBW - bandwidth of resonator channels. Tones are considered collisions if their difference
            is less than this value.
    Returns
    -------
        lo1, lo2 - low and high frequency LOs (in GHz)
    '''
    lfRange = np.array([freqs[0]+1, freqs[0]+1+loRange]) #range to search for LF LO; 200 MHz span
    hfRange = np.array([freqs[-1]-1-loRange, freqs[-1]-1])
    
    nCollisionsOpt = len(freqs) #number of sideband collisions
    nFreqsOmittedOpt = len(freqs) #number of frequencies outside LO band
    costOpt = nCollisionsOpt + colParamWeight*nCollisionsOpt
    for i in range(nIters):
        lo1 = np.random.rand(1)[0]*loRange + lfRange[0]
        hflolb = max(hfRange[0], lo1 + 1) #lower bound of hf sampling range; want LOs to be 1 GHz apart
        lo2 = np.random.rand(1)[0]*(hfRange[1]-hflolb) + hflolb

        #find nFreqsOmitted
        freqsIF1 = freqs - lo1
        freqsIF2 = freqs - lo2
        isInLFBand = np.abs(freqsIF1)<1
        isInHFBand = np.abs(freqsIF2)<1
        isNotValidTone = np.logical_not(np.logical_or(isInLFBand, isInHFBand))
        nFreqsOmitted = np.sum(isNotValidTone)

        #find nCollisions
        freqsIF1 = freqsIF1[np.where(isInLFBand)]
        freqsIF2 = freqsIF2[np.where(isInHFBand)]
        freqsIF1SB = np.sort(np.abs(freqsIF1))
        freqsIF2SB = np.sort(np.abs(freqsIF2))
        nLFColl = np.sum(np.diff(freqsIF1SB)<resBW)
        nHFColl = np.sum(np.diff(freqsIF2SB)<resBW)
        nCollisions = nLFColl + nHFColl

        #pdb.set_trace()

        cost = nFreqsOmitted + colParamWeight*nCollisions
        if cost<costOpt:
            costOpt = cost
            nCollisionsOpt = nCollisions
            nFreqsOmittedOpt = nFreqsOmitted
            lo1Opt = lo1
            lo2Opt = lo2
            #print 'nCollOpt', nCollisionsOpt
            #print 'nFreqsOmittedOpt', nFreqsOmittedOpt
            #print 'los', lo1, lo2

    print 'Optimal nCollisions', nCollisionsOpt
    print 'Optimal nFreqsOmitted', nFreqsOmittedOpt
    print 'LO1', lo1Opt
    print 'LO2', lo2Opt

    return lo1Opt, lo2Opt

modifyTemplarConfigFile(templarConfFn, flNums, roachNums, freqFiles, los, freqBandFlags):
    '''
    Modifies the specified templar config file with the correct frequency lists and los. All files
    are referenced to the MKID_DATA_DIR environment variable. Also changes powersweep_file, longsnap_file, etc
    to be referenced to the correct feedline and MKID_DATA_DIR

    Parameters
    ----------
        templarConfFn - name of templar config file
        flNums - list of feedline numbers corresponding to roachNums
        roachNums - list of board numbers (last 3 digits of roach IP)
        freqFiles - list of frequency file names
        los - list of LO frequencies (in GHz)
        freqBandFlags - list of flags indicating whether board is LF or HF. 'a' for LF and 'b' for HF
    '''
    mdd = os.environ['MKID_DATA_DIR']
    templarConfFn = os.path.join(mdd, templarConfFn)
    tcfp = open(templarConfFn)
    templarConf = ConfigParser.ConfigParser()
    templarConf.readfp(tcfp)
    
    for i,roachNum in enumerate(roachNums):
        templarConf.set('Roach '+str(roachNum), 'freqfile', os.path.join(mdd, freqFiles[i]))
        templarConf.set('Roach '+str(roachNum), 'powersweepfile', os.path.join(mdd, 'ps_r'+str(roachNum)+'FL'+str(flNums[i])+'_'+freqBandFlag+'.h5'))
        templarConf.set('Roach '+str(roachNum), 'longsnapfile', os.path.join(mdd, 'phasesnaps/snap_'+str(roachNum)+'.npz'))
        templarConf.set('Roach '+str(roachNum), 'lo_freq', str(los[i]*1.e9))  

    config.write(templarConfFn)

        

loadClickthroughFile(fn):
    if not os.path.isfile(fn):
        fn = os.path.join(mdd, fn)
    resIDs, locs, freqs = np.loadtxt(fn, unpack=True)
    return resIDs, locs, freqs

findLOsAndMakeFrequencyFile(clickthroughFile, flNum):
    if not os.path.isfile(clickthroughFile):
        clickthroughFile = os.path.join(os.environ['MKID_DATA_DIR'], clickthroughFile))


if __name__=='__main__':
    if len(sys.argv)<3:
        print 'Usage: python findLOsAndMakeFreqFiles.py <setupcfgfile> <templarcfgfile>'
    mdd = os.environ['MKID_DATA_DIR']
    setupDict = readDict()
    setupDict.readFromFile(os.path.join(mdd, sys.argv[1]))
    templarCfgFile = sys.argv[2]
    freqFiles = []
    lfLOs = []
    hfLOs = []

    for i, fl in enumerate(setupDict['feedline_nums']):
        clickthroughFile = os.path.join(mdd, setupDict['clickthrough_files'][i])
        _, _, freqs = loadClickthroughFile(clickthroughFile)
        lo1, lo2 = finLOs(freqs)
        createTemplarResList(clickthroughFile, lo1, lo2, flNum)
        freqFiles.append('freq_FL' + str(fl) + '_a.txt')
        freqFiles.append('freq_FL' + str(fl) + '_b.txt')
        lfLOs.append(lo1)
        hfLOs.append(lo2)

    modifyTemplarConfigFile(templarCfgFile, setupDict['feedline_nums'], setupDict['low_freq_boardnums'], setupDict['high_freq_boardnums'], hfLOs, lfLOs)

