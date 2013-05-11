#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SeedEditor for organ segmentation

Example:

$ seed_editor_qp.py -f head.mat
"""

# import unittest
from optparse import OptionParser
from scipy.io import loadmat
import numpy as np
import sys

from PyQt4.QtCore import Qt, QSize, QPoint
from PyQt4.QtGui import QImage, QDialog, QWidget, QColor,\
    QApplication, QSlider, QPushButton, QGridLayout,\
    QLabel, QPixmap, QPainter, qRgba,\
    QStatusBar, QFont, QComboBox, QIcon, QBitmap

# BGRA order
GRAY_COLORTABLE = np.array([[ii, ii, ii, 255] for ii in range(256)],
                           dtype=np.uint8)

SEEDS_COLORTABLE = np.array([[255, 255, 255, 0],
                             [0, 255, 0, 255],
                             [0, 0, 255, 255]], dtype=np.uint8)

CONTOURS_COLORTABLE = np.array([[255, 255, 255, 0],
                                [255, 0, 0, 64]], dtype=np.uint8)

CONTOURLINES_COLORTABLE = np.array([[255, 255, 255, 0],
                                    [255, 0, 0, 24],
                                    [255, 0, 0, 255]], dtype=np.uint8)

draw_mask = [
    (np.array([[1]], dtype=np.int8), 'small pen'),
    (np.array([[0, 1, 1, 1, 0],
               [1, 1, 1, 1, 1],
               [1, 1, 1, 1, 1],
               [1, 1, 1, 1, 1],
               [0, 1, 1, 1, 0]], dtype=np.int8), 'middle pen'),
    (np.array([[0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0],
               [0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0],
               [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
               [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
               [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
               [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
               [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
               [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
               [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0],
               [0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0],
               [0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0]], dtype=np.int8), 'large pen'),
    ]

box_buttons_seed = {
    Qt.LeftButton: 1,
    Qt.RightButton: 2,
    }

box_buttons_draw = {
    Qt.LeftButton: 1,
    Qt.RightButton: 0,
    }

nei_tab = [[-1, -1], [0, -1], [1, -1],
           [-1, 0], [1, 0],
           [-1, 1], [0, 1], [1, 1]]

    #nei_tab = [[-1, 0], [1, 0]]

def erase_reg(arr, p, val=0):
    buff = [p]

    while len(buff) > 0:
        p = buff.pop()
        row = arr[:,p[1],p[2]]
        ii = p[0]
        while ii >= 0:
            if row[ii] <= 0:
                break

            ii -= 1

        ii += 1

        jj = ii
        while jj < arr.shape[0]:
            if row[jj] <= 0:
                break

            row[jj] = val
            jj +=1

        for inb in nei_tab:
            irow = p[1] + inb[0]
            islice = p[2] + inb[1]
        
            if irow >= 0 and irow < arr.shape[1]\
              and islice >= 0 and islice < arr.shape[2]:
                flag = True
                row = arr[:,irow,islice]
                for kk in np.arange(ii, jj):
                    if flag and row[kk] > 0:
                        buff.append((kk, irow, islice))
                        flag = False
                        continue

                    if flag == False and row[kk] <= 0:
                        flag = True

class SliceBox(QLabel):
    """
    Widget for marking reagions of interest in DICOM slices.
    """
    
    def __init__(self, imageSize, sliceSize, grid,
                 maxVal=1024, minVal=0, mode='seeds'):
        """
        Initialize SliceBox.

        Parameters
        ----------
        imageSize : QSize
            Size of image windows.
        sliceSize : tuple of int
            Size of slice matrix.
        grid : tuple of in
            Pixel size:
            imageSize = (grid_x * sliceSize_x, grid_y * sliceSize_y) 
        maxVal : int
            Maximal value in data (3D) matrix.
        minVal : int
            Minimal value in data (3D) matrix.
        """

        QLabel.__init__(self)

        self.drawing = False
        self.modified = False
        self.seed_mark = None
        self.last_position = None
        self.imagesize = imageSize
        self.grid = grid
        self.slice_size = sliceSize
        self.ctslice_rgba = None
        self.seeds = None
        self.contours = None
        self.max_val = maxVal
        self.min_val = minVal
        self.mask_points = None
        self.erase_region_button = None
        self.erase_fun = None
        self.erase_mode = 'erase_in'
        self.contour_mode = 'fill'


        if mode == 'draw':
            self.seeds_colortable = CONTOURS_COLORTABLE
            self.box_buttons = box_buttons_draw
            self.mode_draw = True

        else:
            self.seeds_colortable = SEEDS_COLORTABLE
            self.box_buttons = box_buttons_seed
            self.mode_draw = False

        self.image = QImage(imageSize, QImage.Format_RGB32)
        self.setPixmap(QPixmap.fromImage(self.image))
        self.setFixedSize(imageSize)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawImage(event.rect(), self.image)
        painter.end()

    def drawSeedMark(self, x, y):
        xx = self.mask_points[0] + x
        yy = self.mask_points[1] + y
        idx = np.arange(len(xx))
        idx[np.where(xx < 0)] = -1
        idx[np.where(xx >= self.slice_size[0])] = -1
        idx[np.where(yy < 0)] = -1
        idx[np.where(yy >= self.slice_size[1])] = -1
        ii = idx[np.where(idx >= 0)]
        xx = xx[ii]
        yy = yy[ii]

        self.seeds[yy, xx] = self.seed_mark

    def setMaskPoints(self, mask):
        self.mask_points = mask

    def drawLine(self, p0, p1):
        """
        Draw line to slice image and seed matrix.

        Parameters
        ----------
        p0 : tuple of int
            Line star point.
        p1 : tuple of int
            Line end point.
        """

        x0, y0 = p0
        x1, y1 = p1
        dx = np.abs(x1-x0)
        dy = np.abs(y1-y0)
        if x0 < x1:
            sx = 1
        else:
            sx = -1

        if y0 < y1:
            sy = 1
        else:
            sy = -1

        err = dx - dy

        while True:
            self.drawSeedMark(x0,y0)

            if x0 == x1 and y0 == y1:
                break

            e2 = 2*err
            if e2 > -dy:
                err = err - dy
                x0 = x0 + sx

            if e2 <  dx:
                err = err + dx
                y0 = y0 + sy

    def drawSeeds(self, pos):
        if pos[0] < 0 or pos[0] >= self.slice_size[0] \
                or pos[1] < 0 or pos[1] >= self.slice_size[1]:
            return

        self.drawLine(self.last_position, pos)
        self.updateSlice()
        
        self.modified = True
        self.last_position = pos

        self.update()

    def arrayToImage(self, arr):
        w, h = self.slice_size
        img = QImage(arr.flatten(), w, h, QImage.Format_ARGB32)

        return img

    def composeRgba(self, bg, fg, cmap):
        idxs = fg.nonzero()

        if idxs[0].shape[0] > 0:
            fg_rgb = cmap[fg[idxs[0]]]
        
            nn = np.prod(bg.shape)
            af = fg_rgb[...,3].astype(np.uint32)
            rgbf = fg_rgb[...,:3].astype(np.uint32)
            rgbb = bg[idxs[0],:3].astype(np.uint32)
        
            rgbx = ((rgbf.T * af).T + (rgbb.T * (255 - af)).T) / 255
            bg[idxs[0],:3] = rgbx.astype(np.uint8)

    def overRgba(self, bg, fg, cmap):
        idxs = fg.nonzero()
        bg[idxs] = cmap[fg[idxs]]

    def get_contours(self, sl):
        cnt = sl.copy()
        chunk = np.zeros((cnt.shape[1] + 2,), dtype=np.int8)
        for irow, row in enumerate(sl):
            chunk[1:-1] = row
            chdiff = np.diff(chunk)
            idx1 = np.where(chdiff > 0)[0]
            if idx1.shape[0] > 0:
                idx2 = np.where(chdiff < 0)[0]
                if idx2.shape[0] > 0:
                    cnt[irow,idx1] = 2
                    cnt[irow,idx2 - 1] = 2

        chunk = np.zeros((cnt.shape[0] + 2,), dtype=np.int8)
        for icol, col in enumerate(sl.T):
            chunk[1:-1] = col
            chdiff = np.diff(chunk)
            idx1 = np.where(chdiff > 0)[0]
            if idx1.shape[0] > 0:
                idx2 = np.where(chdiff < 0)[0]
                if idx2.shape[0] > 0:
                    cnt[idx1,icol] = 2
                    cnt[idx2 - 1,icol] = 2

        return cnt

    def updateSlice(self):

        if self.ctslice_rgba is None:
            return

        img = self.ctslice_rgba.copy()
        w, h = self.slice_size
        n = h * w
        img_as1d = img.reshape((n,4))
        if self.seeds is not None:
            if self.mode_draw:
                if self.contour_mode == 'fill':
                    self.composeRgba(img_as1d, self.seeds.reshape((n,)),
                                     self.seeds_colortable)
                elif self.contour_mode == 'contours':
                    cnt = self.get_contours(self.seeds)
                    self.composeRgba(img_as1d, cnt.reshape((n,)),
                                     CONTOURLINES_COLORTABLE)

            else:
                self.overRgba(img_as1d, self.seeds.reshape((n,)),
                              self.seeds_colortable)

        if self.contours is not None:
            if self.contour_mode == 'fill':
                self.composeRgba(img_as1d, self.contours.reshape((n,)),
                                 CONTOURS_COLORTABLE)

            elif self.contour_mode == 'contours':
                cnt = self.get_contours(self.contours)
                self.composeRgba(img_as1d, cnt.reshape((n,)),
                                 CONTOURLINES_COLORTABLE)

        image = self.arrayToImage(img).scaled(self.imagesize)
        painter = QPainter(self.image)
        painter.drawImage(0, 0, image)
        painter.end()

        self.update()

    def setSlice(self, ctslice=None, seeds=None, contours=None):

        
        if ctslice is not None:
            h, w = ctslice.shape
            n = h * w
            #aux = (ctslice.astype(np.float) / (float(self.max_val + 1) / 255)).astype(np.float)
            aux = ((ctslice.astype(np.float) - float(self.min_val)) * 255 /
                    (float(self.max_val + 1) - float(self.min_val)))
            #print aux.dtype
            aux[aux < 00] = 0
            aux[aux > 255] = 255
            aux=aux.astype(np.uint8)
            self.ctslice_rgba = GRAY_COLORTABLE[aux.reshape((n,))]
            
        if seeds is not None:
            self.seeds = seeds

        if contours is not None:
            self.contours = contours

        self.updateSlice()

    def getSliceSeeds(self):
        if self.modified:
            self.modified = False
            return self.seeds

        else:
            return None

    def eraseRegion(self, pos, mode):
        if self.erase_fun is not None:
            self.erase_fun(pos, mode)
            self.updateSlice()

    def setEraseFun(self, fun):
        self.erase_fun = fun

    def gridPosition(self, pos):
        return (int(pos.x() / self.grid[0]),
                int(pos.y() / self.grid[1]))

    # mouse events
    def mousePressEvent(self, event):
        if event.button() in self.box_buttons:
            self.drawing = True
            self.seed_mark = self.box_buttons[event.button()]
            self.last_position = self.gridPosition(event.pos())

        elif event.button() == Qt.MiddleButton:
            self.drawing = False
            self.erase_region_button = True

    def mouseMoveEvent(self, event):
        if self.drawing:
            self.drawSeeds(self.gridPosition(event.pos()))

    def mouseReleaseEvent(self, event):
        if (event.button() in self.box_buttons) and self.drawing:
            self.drawSeeds(self.gridPosition(event.pos()))
            self.drawing = False

        if event.button() == Qt.MiddleButton\
          and self.erase_region_button == True:
            self.eraseRegion(self.gridPosition(event.pos()),
                             self.erase_mode)

            self.erase_region_button == False
            
    def leaveEvent(self, event):
        self.drawing = False

    def enterEvent(self, event):
        self.drawing = False

class QTSeedEditor(QDialog):
    """
    DICOM viewer and seed editor.
    """

    label_text = {
        'seed': 'inner region - left button, outer region - right button',
        'crop': 'bounds - left button',
        'draw': 'draw - left button, erase - right button, vol. erase - middle button',
        }

    def initUI(self, shape, actualSlice=0,
               maxVal=1024, minVal=0, mode='seed'):
        """
        Initialize UI.

        Parameters
        ----------
        shape : (int, int, int)
            Shape of data matrix.
        actualSlice : int
            Index of actual slice,
            slice_data = data[..., actual_slice]
        maxVal : int
            Maximal value in data (3D) matrix.
        mode : str
            Editor mode.
        """

        # picture
        boxsize = (600, 400)
        slice_grid = np.ceil((boxsize[0] / float(shape[1]),
                              boxsize[1] / float(shape[0])))

        mingrid = np.min(slice_grid)
        slice_grid = np.array([mingrid, mingrid])
        self.slice_box = SliceBox(QSize(shape[1] * slice_grid[0],
                                        shape[0] * slice_grid[1]),
                                  (shape[1], shape[0]), slice_grid,
                                  maxVal, minVal,  mode)

        # slider
        self.n_slices = shape[2]
        self.slider = QSlider(Qt.Vertical)
        self.slider.setValue(actualSlice + 1)
        self.slider.valueChanged.connect(self.selectSlice)
        self.slider.label = QLabel()
        # font = QFont()
        # font.setPointSize(12)
        # font.setBold(True)
        #self.slider.label.setFont(font)
        self.slider.setRange(1, self.n_slices)

        self.volume_label = QLabel('volume [mm3]:\n unknown')

        text = QLabel()
        text.setText(self.label_text[mode])
        # buttons
        btn_quit = QPushButton("Return", self)
        btn_quit.clicked.connect(self.quit)

        btn_prev = QPushButton("down", self)
        btn_prev.clicked.connect(self.slicePrev)
        btn_next = QPushButton("up", self)
        btn_next.clicked.connect(self.sliceNext)
        self.status_bar = QStatusBar()

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.addWidget(text, 0, 0, 1, 5)
        grid.addWidget(self.slice_box, 1, 0, 10, 5)
        grid.addWidget(self.slider, 1, 5, 10, 1)
        grid.addWidget(btn_prev, 2, 7)
        grid.addWidget(btn_next, 1, 7)
        grid.addWidget(self.slider.label, 3, 7)
        grid.addWidget(self.volume_label, 4, 7)

        #self.slice_box.setMaskPoints(([0], [0]))
        combo = QComboBox(self)
        combo.activated.connect(self.changeMask)
        self.mask_points_tab = []
        for mask in draw_mask:
            h, w = mask[0].shape
            xx, yy = mask[0].nonzero()
            self.mask_points_tab.append((xx - w/2, yy - h/2))
            
            img = QImage(w, h, QImage.Format_ARGB32)
            img.fill(qRgba(255, 255, 255, 0))
            for ii in range(xx.shape[0]):
                img.setPixel(xx[ii], yy[ii], qRgba(0, 0, 0, 255))

            img = img.scaled(QSize(w * slice_grid[0], h * slice_grid[1]))
            icon = QIcon(QPixmap.fromImage(img))
            combo.addItem(icon, mask[1])

        self.slice_box.setMaskPoints(self.mask_points_tab[combo.currentIndex()])
        grid.addWidget(combo, 10, 7)

        combo3_options = ['fill', 'contours']
        combo3 = QComboBox(self)
        combo3.activated[str].connect(self.changeContourMode)
        combo3.addItems(combo3_options)
        grid.addWidget(combo3, 9, 7)
        self.changeContourMode(combo3_options[combo3.currentIndex()])

        #if mode not in ['seed','draw','crop']:
        #    raise Exception('Wrong mode' + str(mode))

        if mode == 'seed' and self.mode_fun is not None:
            btn_recalc = QPushButton("Recalculate", self)
            btn_recalc.clicked.connect(self.recalculate)
            grid.addWidget(btn_recalc, 12, 2)

        if mode == 'seed' or mode == 'crop':
            btn_del = QPushButton("Delete", self)
            btn_del.clicked.connect(self.delete)

        if mode == 'draw':
            btn_del = QPushButton("Reset", self)
            btn_del.clicked.connect(self.reset)

            combo2_options = ['erase_in', 'erase_out']
            combo2 = QComboBox(self)
            combo2.activated[str].connect(self.changeEraseMode)
            combo2.addItems(combo2_options)
            grid.addWidget(combo2, 8, 7)
            self.changeEraseMode(combo2_options[combo2.currentIndex()])

        grid.addWidget(btn_del, 12, 0)
        grid.addWidget(btn_quit, 12, 4)
        grid.addWidget(self.status_bar, 13, 0, 1, 9)
        self.setLayout(grid)

        self.setWindowTitle('Segmentation Editor')
        self.status_bar.showMessage("Ready. Min = %.3g, Max %.3g" % 
                (minVal,maxVal)) 
        self.show()

    def __init__(self, img, actualSlice=0,
                 seeds=None, contours=None,
                 mode='seed', modeFun=None,
                 voxelVolume=None, 
                 minVal=None, maxVal=None):
        """
        Initiate Editor

        Parameters
        ----------
        img : array
            DICOM data matrix.
        actualSlice : int
            Index of actual slice.
        seeds : array
            Seeds, user defined regions of interest.
        contours : array
            Computed segmentation.
        mode : str
            Editor modes:
               'seed' - seed editor
               'crop' - manual crop
               'draw' - drawing
        modeFun : fun
            Mode function invoked by user button.
        """

        QDialog.__init__(self)

        self.mode = mode
        self.mode_fun = modeFun

        self.img = img
        self.actual_slice = actualSlice
        self.contours = contours
        self.voxel_volume = voxelVolume
        
        if seeds is None:
            self.seeds = np.zeros(img.shape, np.int8)

        else:
            self.seeds = seeds

        if minVal is None:
            minVal = np.min(img)
        if maxVal is None:
            maxVal = np.max(img)

        self.initUI(img.shape, actualSlice, maxVal, minVal, mode)
        if mode == 'draw':
            self.seeds_orig = self.seeds.copy()
            self.slice_box.setEraseFun(self.eraseRegion)
                    
        self.selectSlice(self.actual_slice + 1)
        
    def recalculate(self, event):
        if np.abs(np.min(self.seeds) - np.max(self.seeds)) < 2:
            self.status_bar.showMessage("Inner and outer regions not defined!")
            return

        self.status_bar.showMessage("Processing...")
        QApplication.processEvents()
        self.mode_fun(self)
        self.selectSlice(self.actual_slice + 1)
        self.status_bar.showMessage("Done")

    def quit(self, event):
        self.close()

    def delete(self, event):
        self.seeds[...,self.actual_slice] = 0
        self.slice_box.setSlice(seeds=self.seeds[...,self.actual_slice])
        self.slice_box.updateSlice()

    def reset(self, event):
        self.seeds[...,self.actual_slice] = self.seeds_orig[...,self.actual_slice]
        self.slice_box.setSlice(seeds=self.seeds[...,self.actual_slice])
        self.slice_box.updateSlice()

    def changeMask(self, val):
        self.slice_box.setMaskPoints(self.mask_points_tab[val])

    def changeContourMode(self, val):
        self.slice_box.contour_mode = str(val)
        self.slice_box.updateSlice()

    def changeEraseMode(self, val):
        self.slice_box.erase_mode = str(val)

    def getBounds(self):
        aux = self.seeds.nonzero()

        if aux[0].nbytes <= 0:
            return None

        else:
            return [[np.min(aux[0]), np.max(aux[0])],
                    [np.min(aux[1]), np.max(aux[1])],
                    [np.min(aux[2]), np.max(aux[2])]]

    def getContoursFromBounds(self, b):
        if b is None:
            return None

        else:
            b = np.array(b)
            b[:,1] += 1
            contours = np.zeros(self.img.shape, np.int8)
            contours[b[0][0]:b[0][1],
                     b[1][0]:b[1][1],
                     b[2][0]:b[2][1]] = 1

            return contours

    def selectSlice(self, value):
        val = value - 1
        if (value < 1) or (value > self.n_slices):
            return

        if (val != self.actual_slice):
            aux = self.slice_box.getSliceSeeds()
            if aux is not None:
                self.seeds[...,self.actual_slice] = aux

        if self.mode == 'crop':
            self.contours = self.getContoursFromBounds(self.getBounds())

        if self.contours is None:
            contours = None

        else:
            contours = self.contours[...,val]

        self.slider.setValue(value)
        self.slider.label.setText('slice: %d' % value)
        self.slice_box.setSlice(self.img[...,val],
                                self.seeds[...,val],
                                contours)

        self.actual_slice = val
        self.updateVolume()

    def slicePrev(self):
        self.selectSlice(self.slider.value() - 1)

    def sliceNext(self):
        self.selectSlice(self.slider.value() + 1)

    def getSeeds(self):
        return self.seeds

    def getContours(self):
        return self.contours

    def getSeedsVal(self, label):
        return self.img[self.seeds==label]

    def setContours(self, contours):
        self.contours = contours
        self.selectSlice(self.actual_slice + 1)

    def eraseRegion(self, pos, mode):
        self.status_bar.showMessage("Processing...")
        QApplication.processEvents()
        x, y = pos
        p = (y, x, self.actual_slice)
        if self.seeds[p] > 0:
            if mode == 'erase_in':
                erase_reg(self.seeds, p, val=0)

            elif mode == 'erase_out':
                erase_reg(self.seeds, p, val=-1)
                idxs = np.where(self.seeds < 0)
                self.seeds.fill(0)
                self.seeds[idxs] = 1
                
        self.status_bar.showMessage("Done")

    def updateVolume(self):
        text = 'volume [mm3]:\n unknown'
        if self.voxel_volume is not None:
            if self.mode == 'draw':
                vd = self.seeds

            else:
                vd = self.contours

            if vd is not None:
                nzs = vd.nonzero()
                nn = nzs[0].shape[0]
                text = 'volume [mm3]:\n %.2e' % (nn * self.voxel_volume)

        self.volume_label.setText(text)

def gen_test():
    test = {}
    test['data'] = np.zeros((10,10,4), dtype=np.uint8)
    test['voxelsizemm'] = (2, 2, 2.5)

    return test

usage = '%prog [options]\n' + __doc__.rstrip()
help = {
    'in_file': 'input *.mat file with "data" field',
    'mode': '"seed" or "crop" mode',
    #'out_file': 'store the output matrix to the file',
    #'debug': 'run in debug mode',
    'gen_test': 'generate test data',
    'test': 'run unit test',
}

def main():
    parser = OptionParser(description='Segmentation editor')
    parser.add_option('-f','--filename', action='store',
                      dest='in_filename', default=None,
                      help=help['in_file'])
    # parser.add_option('-d', '--debug', action='store_true',
    #                   dest='debug', help=help['debug'])
    parser.add_option('-m', '--mode', action='store',
                      dest='mode', default='seed', help=help['mode'])
    parser.add_option('-t', '--tests', action='store_true',
                      dest='unit_test', help=help['test'])
    parser.add_option('-g', '--gener_data', action='store_true',
                      dest='gen_test', help=help['gen_test'])

    # parser.add_option('-o', '--outputfile', action='store',
    #                   dest='out_filename', default='output.mat',
    #                   help=help['out_file'])
    (options, args) = parser.parse_args()

    # if options.tests:
    #     # hack for use argparse and unittest in one module
    #     sys.argv[1:]=[]
    #     unittest.main()

    if options.gen_test:
        dataraw = gen_test()

    else:
        if options.in_filename is None:
            raise IOError('No input data!')

        else:
            dataraw = loadmat(options.in_filename,
                              variable_names=['data', 'voxelsizemm'])
    
    app = QApplication(sys.argv)
    pyed = QTSeedEditor(dataraw['data'],
                        mode=options.mode,
                        voxelVolume=np.prod(dataraw['voxelsizemm']))
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
