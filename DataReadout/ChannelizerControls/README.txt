Feb 25, 2019.  Getting qtTools to work with pyqt5.

Create a new anaconda environment:
$ conda create -n qt5py2 python=2.7.15 anaconda

Activate that environment:
$ conda activate qt5py2

Downgrade the pyqt to pyqt=5.6
$ conda install pyqt=5.6

Install these packages using pip.

pip install katcp==0.6.2
pip install odict
pip install json_tricks
pip install pyqtgraph
   
