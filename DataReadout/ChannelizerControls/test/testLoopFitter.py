import LoopFitter
import pickle
#fn = "2019-03-25-findResonances.pkl"
fn = "2019-02-25-findResonances-v2.pkl"
iqData = pickle.load(open(fn,'rb'))
pfnRoot = "testLoopFitter-02-25-v2"

thresholdFraction = 0.5
rv = LoopFitter.findAndFitResonances(iqData, thresholdFraction, pfnRoot=pfnRoot)
print "rv.keys() =",rv.keys()
