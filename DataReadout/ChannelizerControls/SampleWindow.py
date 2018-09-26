import time
from PyQt4 import QtGui
from PyQt4.QtCore import QThread
from collections import deque
dqToWorker = deque()

class SampleWindow(QtGui.QMainWindow):
    def __init__(self):
        super(SampleWindow, self).__init__()
        
        # Start worker thread
        self.worker = Worker(self)
        self.worker.start()
        
        # Track the number of button clicks
        self.nGo = 0
        
        self.setGeometry(100, 100, 300, 50)
        self.setWindowTitle("SampleWindow")

        self.verticalLayout = QtGui.QVBoxLayout()
        
        self.goButton = QtGui.QPushButton("Go", self)
        self.verticalLayout.addWidget(self.goButton)

        self.goButton.clicked.connect(self.handleGoButton)
        
    def handleGoButton(self):
        self.nGo += 1
        print "handleGoButton: nGo =",self.nGo
        message = "nGo=%d"%self.nGo
        print "emit",message
        dqToWorker.append(message)
        print "done"

class Worker(QThread):
    def __init__(self, parent):
        QThread.__init__(self, parent)
        self.parent = parent

    def run(self):
        while True:
            try:
                message = dqToWorker.popleft()
                print "                 in Worker.run message:",message
                time.sleep(1)
                dqToWorker.clear()
            except IndexError:
                time.sleep(0.1)

        
        
if __name__ == '__main__':
    import sys
    app = QtGui.QApplication(sys.argv)
    window = SampleWindow()
    window.show()
    sys.exit(app.exec_())
    
        
