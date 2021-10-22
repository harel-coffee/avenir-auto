#!/usr/local/bin/python3

# avenir-python: Machine Learning
# Author: Pranab Ghosh
# 
# Licensed under the Apache License, Version 2.0 (the "License"); you
# may not use this file except in compliance with the License. You may
# obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0 
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.

import sys
import random 
import time
import math
import numpy as np
import statistics 


# histogram class
class Histogram:
	def __init__(self, min, binWidth):
		self.xmin = min
		self.binWidth = binWidth
	
	# create with bins already created	
	@classmethod
	def createInitialized(cls, min, binWidth, values):
		instance = cls(min, binWidth)
		instance.xmax = min + binWidth * (len(values) - 1)
		instance.ymin = 0
		instance.bins = np.array(values)
		instance.fmax = 0
		for v in values:
			if (v > instance.fmax):
				instance.fmax = v
		instance.ymin = 0.0
		instance.ymax = instance.fmax
		return instance
	
	# create with un initialized bins
	@classmethod
	def createUninitialized(cls, min, max, binWidth):
		instance = cls(min, binWidth)
		instance.xmax = max
		instance.numBin = (max - min) / binWidth + 1
		instance.bins = np.zeros(instance.numBin)
		return instance
	
	def initialize(self):
		self.bins = np.zeros(self.numBin)
		
	# add a value to a bin	
	def add(self, value):
		bin = (value - self.xmin) / self.binWidth
		if (bin < 0 or  bin > self.numBin - 1):
			print (bin)
			raise ValueError("outside histogram range")
		self.bins[bin] += 1.0
	
	# normalize 	
	def normalize(self):
		total = self.bins.sum()
		self.bins = np.divide(self.bins, total)
	
	
	# cumulative dists
	def cumDistr(self):
		self.cbins = np.cumsum(self.bins)
	
	# return value corresponding to a percentile	
	def percentile(self, percent):
		if self.cbins is None:
			raise ValueError("cumulative distribution is not available")
			
		for i,cuml in enumerate(self.cbins):
			if percent > cuml:
				value = (i * self.binWidth) - (self.binWidth / 2) + \
				(percent - self.cbins[i-1]) * self.binWidth / (self.cbins[i] - self.cbins[i-1]) 
				break
		return value
		
	# return max bin value	
	def max(self):
		return self.bins.max()
	
	# return a bin value	
	def value(self, x):
		bin = int((x - self.xmin) / self.binWidth)
		f = self.bins[bin]
		return f
	
	def cumValue(self, x):
		bin = int((x - self.xmin) / self.binWidth)
		c = self.cbins[bin]
		return c
	
		
	def getMinMax(self):
		return (self.xmin, self.xmax)
		
	def boundedValue(self, x):
		if x < self.xmin:
			x = self.xmin
		elif x > self.xmax:
			x = self.xmax
		return x

class RunningStat:
	"""
	running stat class
	"""
	def __init__(self):
		self.sum = 0.0
		self.sumSq = 0.0
		self.count = 0
	
	@staticmethod
	def create(count, sum, sumSq):
		rs = RunningStat()
		rs.sum = sum
		rs.sumSq = sumSq
		rs.count = count
		return rs
		
	def add(self, value):
		"""
		adds new value
		"""
		self.sum += value
		self.sumSq += (value * value)
		self.count += 1

	def getStat(self):
		"""
		calculate mean and std deviation 
		"""
		mean = self.sum /self. count
		t = self.sumSq / (self.count - 1) - mean * mean * self.count / (self.count - 1)
		sd = math.sqrt(t)
		re = (mean, sd)
		return re

	def addGetStat(self,value):
		"""
		calculate mean and std deviation with new value added
		"""
		self.add(value)
		re = self.getStat()
		return re
	
	def getCount(self):
		"""
		return count
		"""
		return self.count
	
	def getState(self):
		"""
		return state
		"""
		s = (self.count, self.sum, self.sumSq)
		return s
		

class SlidingWindowStat:
	"""
	sliding window stat 
	"""
	def __init__(self):
		self.sum = 0.0
		self.sumSq = 0.0
		self.count = 0
		self.values = None
	
	@staticmethod
	def create(values, sum, sumSq):
		sws = SlidingWindowStat()
		sws.sum = sum
		sws.sumSq = sumSq
		self.values = values.copy()
		sws.count = len(self.values)
		return sws
		
	@staticmethod
	def initialize(values):
		sws = SlidingWindowStat()
		sws.values = values.copy()
		for v in sws.values:
			sws.sum += v
			sws.sumSq += v * v		
		sws.count = len(sws.values)
		return sws

	@staticmethod
	def createEmpty(count):
		sws = SlidingWindowStat()
		sws.count = count
		sws.values = list()
		return sws

	def add(self, value):
		"""
		adds new value
		"""
		self.values.append(value)		
		if len(self.values) > self.count:
			self.sum = self.sum + value - self.values[0]
			self.sumSq = self.sumSq  + (value * value) - (self.values[0] * self.values[0])
			self.values.pop(0)
		else:
			self.sum = self.sum + value
			self.sumSq = self.sumSq  + (value * value)
		

	def getStat(self):
		"""
		calculate mean and std deviation 
		"""
		mean = self.sum /self. count
		t = self.sumSq / (self.count - 1) - mean * mean * self.count / (self.count - 1)
		sd = math.sqrt(t)
		re = (mean, sd)
		return re

	def addGetStat(self,value):
		"""
		calculate mean and std deviation with new value added
		"""
		self.add(value)
		re = self.getStat()
		return re
	
	def getCount(self):
		"""
		return count
		"""
		return self.count
	
	def getCurSize(self):
		"""
		return count
		"""
		return len(self.values)
		
	def getState(self):
		"""
		return state
		"""
		s = (self.count, self.sum, self.sumSq)
		return s
		

def basicStat(ldata):
	"""
	mean and std dev
	"""
	m = statistics.mean(ldata)
	s = statistics.stdev(ldata, xbar=m)
	r = (m, s)
	return r
		