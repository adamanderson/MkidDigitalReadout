"""
Demonstrate communicating to a worker thread with a deque.

The main window appends a message to the deque and then carries on without delay.
In this implementation, if you mash the "Go" button before the worker is done, it ignores
the extra clicks by clearing the deque when it is done processing.  

This can be run from ipython like this:

$ ipython --gui=qt

In [1]: import qtTools

In [2]: qtTools.sampleWindow()
Out[2]: <SampleWindow.SampleWindow at 0x7f5feec8ddf8>

In [3]: handleGoButton: nGo = 1
emit nGo=1

... etc.

Or it can be run from the command line:

$ python SampleWindow.py

"""

import time
from PyQt5 import QtGui
from PyQt5.QtCore import QThread
from collections import deque
dqToWorker = deque()

class SampleWindow(QtGui.QMainWindow):
    """The main window, with a single button."""
    def __init__(self):
        """
        Start the worker thread, counts the number of clicks, and 
        create the "Go" button.
        """
        super(SampleWindow, self).__init__()
        
        # Start worker thread
        self.worker = Worker(self)
        self.worker.start()
        
        # Track the number of button clicks
        self.nGo = 0

        # Make a button
        self.setGeometry(100, 100, 300, 50)
        self.setWindowTitle("SampleWindow")
        self.verticalLayout = QtGui.QVBoxLayout()        
        self.goButton = QtGui.QPushButton("Go", self)
        self.verticalLayout.addWidget(self.goButton)

        # Make the button do something when it is clicked
        self.goButton.clicked.connect(self.handleGoButton)
        
    def handleGoButton(self):
        """
        Increment ment self.nGo and put a message on the deque to the Worker thread
        """
        self.nGo += 1
        print "handleGoButton: nGo =",self.nGo
        message = "nGo=%d"%self.nGo
        print "emit",message
        dqToWorker.append(message)
        print "done"

class Worker(QThread):
    """
    The Worker Thread, that only sleeps.
    """
    def __init__(self, parent):
        """ Initialize.  Remember who your parent is.  Not needed in this example."""
        QThread.__init__(self, parent)
        self.parent = parent

    def run(self):
        """
        Stay in this loop.  Get messages from the dequeue.
        Pretend that you are doing work that takes one second by sleeping.
        Once that is done, clear the deque so you don't wind up sleeping many times.
        """
        while True:
            try:
                message = dqToWorker.popleft()
                print "                 in Worker.run message:",message
                time.sleep(1)
                dqToWorker.clear()
            except IndexError:
                time.sleep(0.1)
            except AttributeError: # This happens when stopping
                if dqToWorker is None:
                    break
        
        
if __name__ == '__main__':
    import sys
    app = QtGui.QApplication(sys.argv)
    window = SampleWindow()
    window.show()
    sys.exit(app.exec_())
    
        
