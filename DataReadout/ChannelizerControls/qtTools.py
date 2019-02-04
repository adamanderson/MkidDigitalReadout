'''

Tools to plot using qt, using the "rchc" from clTools.setup, 
All communication with the roach board is via functions defined in clTools.

'''
import clTools
reload(clTools)
import MultiToneScannerWindow
reload(MultiToneScannerWindow)
import FindResonancesWindow
reload(FindResonancesWindow)
import PlotPhaseStreamWindow
reload(PlotPhaseStreamWindow)
import IQPlotWindow
reload(IQPlotWindow)
import PhasePlotWindow
reload(PhasePlotWindow)
import ResonancePlotWindow
reload(ResonancePlotWindow)
import SampleWindow
reload(SampleWindow)
from PyQt4 import QtGui

if QtGui.QApplication.type() == 0:
    print """
Warning:  QtGui.QApplication is not running.
QT Windows will not work, and the entire session will crash if you try.
Here are two things you could do:
1)  Start ipython like this:  'ipython --gui=qt'
or
2)  Add this line:
c.TerminalIPythonApp.gui = 'qt'
to your ipython configuration file, which is probably 
~/.python/profile_default/ipython_config.py 

Changing the configuration file usually works.  When it does not, use the --gui=qt switch
    """
    
def multiToneScanner(rchc, iqData=None):
    reload(MultiToneScannerWindow)
    multiToneScannerWindow = MultiToneScannerWindow.\
                           MultiToneScannerWindow(rchc, iqData)
    multiToneScannerWindow.show()
    return multiToneScannerWindow

def findResonances(rchc):
    reload(FindResonancesWindow)
    findResonancesWindow = FindResonancesWindow.\
                           FindResonancesWindow(rchc)
    findResonancesWindow.show()
    return findResonancesWindow

def plotPhaseStream(rchc):
    reload(PlotPhaseStreamWindow)
    plotPhaseStreamWindow = PlotPhaseStreamWindow.\
                           PlotPhaseStreamWindow(rchc)
    plotPhaseStreamWindow.show()
    return plotPhaseStreamWindow

def plotIQ(rchc):
    reload(IQPlotWindow)
    iqPlotWindow = IQPlotWindow.IQPlotWindow(rchc)
    iqPlotWindow.show()
    return iqPlotWindow

def plotPhases(rchc):
    reload(PhasePlotWindow)
    phasePlotWindow = PhasePlotWindow.PhasePlotWindow(rchc)
    phasePlotWindow.show()
    return phasePlotWindow

def plotResonances(rchc):
    reload(ResonancePlotWindow)
    resonancePlotWindow = ResonancePlotWindow.ResonancePlotWindow(rchc)
    resonancePlotWindow.show()
    return resonancePlotWindow

def plotDemo():
    """
    Demonstrate that qt is working.

    Usage:
    > w = qtTools.plotDemo()

    To close the window, either use the "x" button on it, or

    > w.close()
    """
    widget = QtGui.QWidget()
    label = QtGui.QLabel(widget)
    label.setText("Hello from qtTools.plotDemo()")
    widget.setWindowTitle("qtTools.plotDemo")
    widget.setGeometry(100, 100, 300, 50)
    label.move(50,20)
    widget.show()
    return widget

def sampleWindow():
    sampleWindow = SampleWindow.SampleWindow()
    sampleWindow.show()
    return sampleWindow
