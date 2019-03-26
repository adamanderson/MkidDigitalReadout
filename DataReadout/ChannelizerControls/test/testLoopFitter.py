import LoopFitter
import pickle
fn = "2019-03-25-findResonances.pkl"
iqData = pickle.load(open(fn,'rb'))
pfnRoot = "testLoopFitter"

thresholdFraction = 0.5
rv = LoopFitter.findAndFitResonances(iqData, thresholdFraction, pfnRoot=pfnRoot)
print "rv.keys() =",rv.keys()
