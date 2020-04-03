#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

This module holds functions to import scanimage tiff files and gather the meta info stored in the headers. With thanks to Tobias Rose for some of the regular expressions.

Requires ScanImageTiffReader and re (regular expressions)
https://vidriotech.gitlab.io/scanimagetiffreader-python/

Created on Thu Jan 30, 2020

@author: pgoltstein
"""

# =============================================================================
# Imports

import os, glob
import re
import numpy as np
from alive_progress import alive_bar
from ScanImageTiffReader import ScanImageTiffReader
import argparse


# =============================================================================
# Arguments

parser = argparse.ArgumentParser( description = "This module holds a dataclass calles imagestack and supporting functions. The main functionality is to handle imagestacks. Meta data can be accessed using simple dot-reference properties. Any slice of image data can be directly loaded from disk using Python's standard method of indexing slices directly on the imagestack class. Currently it supports stacks of scanimage tiff files only. With thanks to Tobias Rose for some of the regular expressions. The module can run from the command line for testing. \n (written by Pieter Goltstein - February 2020)")
parser.add_argument('filepath', type=str, help= 'path to the tiff folder')
parser.add_argument('filestem', type=str, help= 'filestem of tiffs')
args = parser.parse_args()


# =============================================================================
# Functions

def parseheader(header):
    """ This function reads the most relevant information from the tiff header of a scanimage tiff.
        Inputs
        - header: The can be obtained from ScanImageTiffReader, header (tifffile.description(0))
        Returns
        - si_info: A dictionary holding the scanimage named variables in python format (int, float, list[floats])
    """

    # Define the regular expressions needed to extract the information
    rx_dict = {
        "stackNumSlices": re.compile(r'stackNumSlices = (?P<stackNumSlices>\d+)'),
        "scanZoomFactor": re.compile(r'scanZoomFactor = (?P<scanZoomFactor>\d+.?\d*)'),
        "scanFrameRate": re.compile(r'scanFrameRate = (?P<scanFrameRate>\d+.?\d*)'),
        "channelsSave": re.compile(r'channelsSave = (?P<channelsSave>\d+)'),
        "fastZNumVolumes": re.compile(r'fastZNumVolumes = (?P<fastZNumVolumes>\d+)'),
        "triggerClockTimeFirst": re.compile(r'triggerClockTimeFirst = (?P<triggerClockTimeFirst>\'\d+-\d+-\d+ \d+:\d+:\d+.\d+\')'),
        "loggingFramesPerFile": re.compile(r'loggingFramesPerFile = (?P<loggingFramesPerFile>\d+)'),
        "beamPowers": re.compile(r'beamPowers = (?P<beamPowers>\d+.?\d*)'),
        "loggingFileStem": re.compile(r'loggingFileStem = (?P<loggingFileStem>\'.+\')'),
        "motorPosition": re.compile(r'motorPosition = (?P<motorPosition>\[.+\])'),
        "pmtGain": re.compile(r'pmtGain = (?P<pmtGain>\[.+\])'),
        "scanLinesPerFrame": re.compile(r'scanLinesPerFrame = (?P<scanLinesPerFrame>\d+)'),
        "scanPixelsPerLine": re.compile(r'scanPixelsPerLine = (?P<scanPixelsPerLine>\d+)'),
        "stackZEndPos": re.compile(r'stackZEndPos = (?P<stackZEndPos>\d+.?\d*)'),
        "stackZStartPos": re.compile(r'stackZStartPos = (?P<stackZStartPos>\d+.?\d*)'),
        "stackZStepSize": re.compile(r'stackZStepSize = (?P<stackZStepSize>\d+.?\d*)'),
    }

    # Now step through the dictionary and extract the information as int, float, string or a list of floats
    si_info = {}
    for key, rx in rx_dict.items():
        # Find match using reg-ex
        match = rx_dict[key].search(header)
        if match:
            # floating point numbers
            if key in ["scanZoomFactor", "scanFrameRate", "beamPowers", "stackZEndPos", "stackZStartPos", "stackZStepSize"]:
                si_info[key] = float(match.group(key))
            # strings
            elif key in ["triggerClockTimeFirst","loggingFileStem"]:
                si_info[key] = str(match.group(key)).strip('\'')
            # list of floats
            elif key in ["motorPosition","pmtGain"]:
                positions = str(match.group(key)).strip('[]')
                si_info[key] = []
                for pos in positions.split(' '):
                    si_info[key].append(float(pos))
            # otherwise integer
            else:
                si_info[key] = int(match.group(key))
        # if no reasonable match found, assign None
        else:
            si_info[key] = None

    # Return the dict
    return si_info


# =============================================================================
# Classes

class imagestack(object):
    """ This class represents an entire (multi-tiff) scanimage stack. Image channel and image plane should be set manually (defaults are 0).

        The class can load the image data using standard np.ndarray indexing:
         * data = imagestack[:] returns all the data
         * data = imagestack[1] returns the second frame (zero based slice)
         * data = imagestack[[5,8,10]] returns frames 5,8 and 10
         * data = imagestack[::2] returns every second frame.

         In addition, the class has several methods for accessing the meta data, which can be accessed as properties. For instance:
         * res = imagestack.resolution returns the [y,x] image resolution
         * nchannels = imagestack.nchannels returns number of image channels
    """

    def __init__(self, filestem='', filepath=None, extention="tif"):
        """ Initializes the image stack and gathers the meta data
            Inputs
            - filestem: Part of the file name that is shared among all tiffs belonging to the stack (optional, if left out all tiffs in filepath will be included)
            - filepath: Full directory path to the tiffs
            - extention: file extention of the stack
        """

        # Set the filepath
        if filepath is not None:
            self.filepath = filepath
        else:
            self.filepath = os.getcwd()

        # Find the tiff files
        self.block_files = sorted( glob.glob( os.path.join( self.filepath, filestem+'*.'+extention ) ) )
        self._nblocks = len(self.block_files)
        print("Imagestack of {} {} files, using filestem {}".format( self._nblocks, extention, filestem+'*.'+extention))

        # Load and parse the header
        with ScanImageTiffReader( self.block_files[0] ) as tifffile:
            header = (tifffile.description(0))
            self.si_info = parseheader(header)
        self._nframesperblock = self.si_info["loggingFramesPerFile"]
        print("{} frames, {} planes, {} channels, {} x {} pixels".format( self.nframes, self.nplanes, self.nchannels, self.yres, self.xres ))

        # Default settings of internal variables
        self._datatype = np.int16
        self._channel = 0
        self._plane = 0

    @property
    def xres(self):
        """ Number of pixels along the x-axis """
        return self.si_info["scanPixelsPerLine"]

    @property
    def yres(self):
        """ Number of pixels along the y-axis """
        return self.si_info["scanLinesPerFrame"]

    @property
    def resolution(self):
        """ Number of pixels along the y- and x-axis """
        return self.si_info["scanLinesPerFrame"], self.si_info["scanPixelsPerLine"]

    @property
    def nframes(self):
        """ Number of frames per slice and channel """
        return self.si_info["fastZNumVolumes"]

    @property
    def nplanes(self):
        """ Number of planes """
        return self.si_info["stackNumSlices"]

    @property
    def nchannels(self):
        """ Number of channels """
        return self.si_info["channelsSave"]

    @property
    def channel(self):
        """ Returns the currently selected channel """
        return self._channel

    @channel.setter
    def channel(self,chan_nr):
        """ Sets the channel """
        self._channel = int(chan_nr)

    @property
    def plane(self):
        """ Returns the currently selected image plane """
        return self._plane

    @plane.setter
    def plane(self,plane_nr):
        """ Sets the plane """
        self._plane = int(plane_nr)

    def __getitem__(self, indices):
        """ Loads and returns the image data directly from disk """

        # Use the provided slice object to get the requested frames
        if isinstance(indices, slice):
            frames = np.arange(self.nframes)[indices]
        elif isinstance(indices, list) or isinstance(indices, tuple):
            frames = np.array(indices)
        else:
            frames = np.array([indices,])

        # Define the indices of the requested frames
        # tiffs are stored as [ch0-sl0, ch1-sl0, ch0-sl1, ch2-sl1, ch0-sl2 etc]
        start_frame = (self._plane * self.nchannels) + self._channel
        frame_jump = self.nchannels * self.nplanes
        frame_ixs = frames * frame_jump
        n_frame_ixs = len(frame_ixs)
        frame_ids = np.arange(n_frame_ixs)

        # Identify the block files to open, and which frames to load
        block_ixs_per_frame = np.floor(frame_ixs / self._nframesperblock).astype(np.int)
        frame_ixs_in_block = np.mod(frame_ixs, self._nframesperblock)
        block_numbers,block_inverse = np.unique(block_ixs_per_frame, return_inverse=True)
        block_indexes = list(range(len(block_numbers)))

        # Split the list of frames into a per-block list
        frame_ixs_per_block = []
        frame_ids_per_block = []
        for b in block_indexes:
            frame_ixs_per_block.append( list(frame_ixs_in_block[block_inverse==b]) )
            frame_ids_per_block.append( list(frame_ids[block_inverse==b]) )

        # Loop block files, and frame indices to load all requested frames
        imagedata = np.zeros((self.yres,self.xres,n_frame_ixs),dtype=self._datatype)
        with alive_bar(n_frame_ixs) as bar:
            for bnr,bix in zip(block_numbers,block_indexes):
                with ScanImageTiffReader(self.block_files[bnr]) as tifffile:
                    for ix,id_ in zip( frame_ixs_per_block[bix], frame_ids_per_block[bix] ):
                        imagedata[:,:,id_] = tifffile.data(beg=ix,end=ix+1)
                        bar()

        # Return the stack
        return imagedata

# =============================================================================
# Main, for testing from command line

if __name__ == '__main__':
    im = imagestack(filestem=args.filestem, filepath=args.filepath, extention="tif")
    a=im[[3,4,5]]
    # a=im[3]
    # a=im[:100]
    # a=im[-100:]
    # a=im[-200:-100:2]
    # a=im[::25]
