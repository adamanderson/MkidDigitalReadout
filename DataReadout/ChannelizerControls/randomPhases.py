import struct
import numpy as np
import matplotlib.pyplot as plt

def getRandomPhasesSimple(freqs, deltaSeed=0):
    phases = np.zeros(len(freqs),dtype=np.double)
    seeds = np.zeros(len(freqs),dtype=np.uint32)
    np.random.seed(deltaSeed)
    for i,freq in enumerate(freqs):
        s = struct.pack(">f",freq)
        sint = struct.unpack('<L', s)[0]
        seed = deltaSeed
        seeds[i] = seed
        phases[i] = np.random.uniform(0,2*np.pi)
    return {"phases":phases,"seeds":seeds}

def getRandomPhases(freqs, deltaSeed=0):
    print "Hello from randomPhases.getRandomPhases"
    phases = np.zeros(len(freqs),dtype=np.double)
    seeds = np.zeros(len(freqs),dtype=np.uint32)
    for i,freq in enumerate(freqs):
        s = struct.pack(">f",freq)
        sint = struct.unpack('<L', s)[0]
        seed = (sint+245705361*deltaSeed)%4294967295
        seeds[i] = seed
        np.random.seed(seed)
        phases[i] = np.random.uniform(0,2*np.pi)
    return {"phases":phases,"seeds":seeds}

if __name__ == "__main__":

    # This is a typical list of frequencies
    # Generate random phases for 10000 trials.  Plots the phases to show
    # that they are uniformly distributed between 0 and 2pi.
    # Also track the random number seeds used, and show that there are
    # uniformly distributed from 0 to the max value of 4294967295
    text = """
    4.82315704300e+09 4.84861633300e+09 4.88052246100e+09 4.90685913100e+09
    4.82552215600e+09 4.84909698500e+09 4.88206359900e+09 4.90726348900e+09
    4.82697937000e+09 4.85002014200e+09 4.88407775900e+09 4.90974304200e+09
    4.82790252700e+09 4.85253784200e+09 4.88529846200e+09 4.91096374500e+09
    4.82938262900e+09 4.85600158700e+09 4.88773986800e+09 4.91407653800e+09
    4.83208343500e+09 4.85768005400e+09 4.88982269300e+09 4.91566345200e+09
    4.83444091800e+09 4.85961792000e+09 4.89144012500e+09 4.91779968300e+09
    4.83535644500e+09 4.86044189500e+09 4.89311096200e+09 4.91998168900e+09
    4.83801910400e+09 4.86347839400e+09 4.89489624000e+09 4.92210266100e+09
    4.83921691900e+09 4.86485931400e+09 4.89710113500e+09 4.92395660400e+09
    4.84071991000e+09 4.86621734600e+09 4.89897796600e+09 4.92548248300e+09
    4.84310028100e+09 4.86813995400e+09 4.90083953900e+09 4.92635986300e+09
    4.84476348900e+09 4.86980316200e+09 4.90196106000e+09 4.92858001700e+09
    4.84648010300e+09 4.87070343000e+09 4.90408203100e+09 4.92980072000e+09
    4.84699127200e+09 4.87218353300e+09 4.90536377000e+09 4.93251678500e+09
    4.84760162400e+09 4.87360260000e+09 4.90618011500e+09 -1.00000000000e+0
    """

    freqs = []
    for v in text.replace("\n", ' ').split(' '):
        try:
            freqs.append(float(v))
        except:
            pass

    hSum = None
    sSum = None
    
    for deltaSeed in range(10000):
        retval = getRandomPhases(freqs, deltaSeed=deltaSeed)
        rp = retval['phases']
        hist,bin_edges = np.histogram(rp, bins=10000, range=(0,2*np.pi))
        if hSum is None:
            hSum = hist
        else:
            hSum += hist

        sHist, sBin_edges = np.histogram(
            retval['seeds'], bins=10000, range=(0,2**32))
        if sSum is None:
            sSum = sHist
        else:
            sSum += sHist

    centers = 0.5*(bin_edges[:-1]+bin_edges[1:])
    sCenters = 0.5*(sBin_edges[:-1]+sBin_edges[1:])
    fig,ax = plt.subplots(2,2)

    ax[0][0].plot(centers, hSum)
    #hhp, hhb = np.histogram(hSum, bins=70, range=(30,100))
    #print "bin width = ",hhb[0],hhb[1]
    #ax[0][1].plot(0.5*(hhb[:-1]+hhb[1:]),hhp)
    ax[0][1].hist(hSum, bins=70, range=(30,100))
    ax[1][0].plot(sCenters, sSum)
    ax[1][1].hist(sSum, bins=70, range=(30,100))

    plt.savefig("randomPhases.png",dpi=300)

