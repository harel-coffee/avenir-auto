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

# Package imports
import os
import sys
import matplotlib.pyplot as plt
import numpy as np
import torch
from torch.autograd import Variable
from torch.utils.data import Dataset, TensorDataset
from torch.utils.data import DataLoader
import sklearn as sk
from sklearn.neighbors import KDTree
import matplotlib
import random
import jprops
from random import randint
import statistics
sys.path.append(os.path.abspath("../lib"))
from util import *
from mlutil import *


class FeedForwardNetwork(torch.nn.Module):
	def __init__(self, configFile, addDefValues=None):
		"""
    	In the constructor we instantiate two nn.Linear modules and assign them as
    	member variables.
		"""
		defValues = dict() if addDefValues is None else addDefValues.copy()
		defValues["common.mode"] = ("training", None)
		defValues["common.model.directory"] = ("model", None)
		defValues["common.model.file"] = (None, None)
		defValues["common.preprocessing"] = (None, None)
		defValues["common.scaling.method"] = ("zscale", None)
		defValues["common.verbose"] = (False, None)
		defValues["train.data.file"] = (None, "missing training data file")
		defValues["train.data.fields"] = (None, "missing training data field ordinals")
		defValues["train.data.feature.fields"] = (None, "missing training data feature field ordinals")
		defValues["train.data.out.fields"] = (None, "missing training data feature field ordinals")
		defValues["train.layer.data"] = (None, "missing layer data")
		defValues["train.output.size"] = (None, "missing  output size")
		defValues["train.batch.size"] = (10, None)
		defValues["train.loss.reduction"] = ("mean", None)
		defValues["train.num.iterations"] = (500, None)
		defValues["train.lossFn"] = ("mse", None) 
		defValues["train.optimizer"] = ("sgd", None) 
		defValues["train.opt.learning.rate"] = (.0001, None)
		defValues["train.opt.weight.decay"] = (0, None) 
		defValues["train.opt.momentum"] = (0, None) 
		defValues["train.opt.eps"] = (1e-08, None) 
		defValues["train.opt.dampening"] = (0, None) 
		defValues["train.opt.momentum.nesterov"] = (False, None) 
		defValues["train.opt.betas"] = ([0.9, 0.999], None) 
		defValues["train.opt.alpha"] = (0.99, None) 
		defValues["train.save.model"] = (False, None) 
		defValues["train.track.error"] = (False, None) 
		defValues["train.epoch.intv"] = (5, None) 
		defValues["train.batch.intv"] = (5, None) 
		defValues["train.print.weights"] = (False, None) 
		defValues["valid.data.file"] = (None, None)
		defValues["valid.accuracy.metric"] = (None, None)
		defValues["predict.data.file"] = (None, None)
		defValues["predict.use.saved.model"] = (True, None)
		defValues["predict.output"] = ("binary", None)
		defValues["predict.feat.pad.size"] = (60, None)
		defValues["predict.print.output"] = (True, None)
		defValues["calibrate.num.bins"] = (10, None)
		defValues["calibrate.pred.prob.thresh"] = (0.5, None)
		defValues["calibrate.num.nearest.neighbors"] = (10, None)
		self.config = Configuration(configFile, defValues)
		
		super(FeedForwardNetwork, self).__init__()
    	
	def setConfigParam(self, name, value):
		"""
		set config param
		"""
		self.config.setParam(name, value)

	def getConfig(self):
		"""
		get config object
		"""
		return self.config

	def setVerbose(self, verbose):
		self.verbose = verbose
		
	def buildModel(self):
		"""
    	Loads configuration and builds the various piecess necessary for the model
		"""
		torch.manual_seed(9999)

		self.verbose = self.config.getStringConfig("common.verbose")[0]
		numinp = len(self.config.getIntListConfig("train.data.feature.fields")[0])
		#numOut = len(self.config.getStringConfig("train.data.out.fields")[0].split(","))
		self.outputSize = self.config.getIntConfig("train.output.size")[0]
		self.batchSize = self.config.getIntConfig("train.batch.size")[0]
		#lossRed = self.config.getStringConfig("train.loss.reduction")[0]
		#learnRate = self.config.getFloatConfig("train.opt.learning.rate")[0]
		self.numIter = self.config.getIntConfig("train.num.iterations")[0]
		optimizer = self.config.getStringConfig("train.optimizer")[0]
		self.lossFnStr = self.config.getStringConfig("train.lossFn")[0]
		self.accMetric = self.config.getStringConfig("valid.accuracy.metric")[0]
		self.trackErr = self.config.getBooleanConfig("train.track.error")[0]
		self.batchIntv = self.config.getIntConfig("train.batch.intv")[0]
		self.restored = False
		
		#build network
		layers = list()
		ninp = numinp
		trData =  self.config.getStringConfig("train.layer.data")[0].split(",")
		for ld in trData:
			lde = ld.split(":")
			assert len(lde) == 5, "expecting 5 items for layer data"
			
			#num of units, activation, whether batch normalize, whether batch normalize after activation, dropout fraction
			nunit = int(lde[0])
			actStr = lde[1]
			act = FeedForwardNetwork.createActivation(actStr) if actStr != "none"  else None
			bnorm = lde[2] == "true"
			afterAct = lde[3] == "true"
			dpr = float(lde[4])
			
			layers.append(torch.nn.Linear(ninp, nunit))			
			if bnorm:
				#with batch norm
				if afterAct:
					safeAppend(layers, act)
					layers.append(torch.nn.BatchNorm1d(nunit))
				else:
					layers.append(torch.nn.BatchNorm1d(nunit))
					safeAppend(layers, act)
			else:
				#without batch norm
				safeAppend(layers, act)
			
			if dpr > 0:
				layers.append(torch.nn.Dropout(dpr))
			ninp = nunit
			
		self.layers = torch.nn.Sequential(*layers)	
		
		#training data
		dataFile = self.config.getStringConfig("train.data.file")[0]
		(featData, outData) = FeedForwardNetwork.prepData(self, dataFile)
		self.featData = torch.from_numpy(featData)
		self.outData = torch.from_numpy(outData)

		#validation data
		dataFile = self.config.getStringConfig("valid.data.file")[0]
		(featDataV, outDataV) = FeedForwardNetwork.prepData(self, dataFile)
		self.validFeatData = torch.from_numpy(featDataV)
		self.validOutData = outDataV

		# loss function and optimizer
		self.lossFn = FeedForwardNetwork.createLossFunction(self, self.lossFnStr)
		self.optimizer =  FeedForwardNetwork.createOptimizer(self, optimizer)
		
		self.yPred  = None
		
	def setValidationData(self, dataSource):
		"""
		sets validation data
		"""
		(featDataV, outDataV) = FeedForwardNetwork.prepData(self, dataSource)
		self.validFeatData = torch.from_numpy(featDataV)
		self.validOutData = outDataV
 	
	@staticmethod
	def createActivation(actName):
		"""
		create activation
		"""
		if actName is None:
			activation = None
		elif actName == "relu":
			activation = torch.nn.ReLU()
		elif actName == "tanh":
			activation = torch.nn.Tanh()
		elif actName == "sigmoid":
			activation = torch.nn.Sigmoid()
		elif actName == "softmax":
			activation = torch.nn.Softmax(dim=1)
		else:
			exitWithMsg("invalid activation function name " + actName)
		return activation

	@staticmethod
	def createLossFunction(model, lossFnName):
		"""
		create loss function
		"""
		config = model.config
		lossRed = config.getStringConfig("train.loss.reduction")[0]
		if lossFnName == "ltwo" or lossFnName == "mse":
			lossFunc = torch.nn.MSELoss(reduction=lossRed)
		elif lossFnName == "ce":
			lossFunc = torch.nn.CrossEntropyLoss(reduction=lossRed)
		elif lossFnName == "lone" or lossFnName == "mae":
			lossFunc = torch.nn.L1Loss(reduction=lossRed)
		elif lossFnName == "bce":
			lossFunc = torch.nn.BCELoss(reduction=lossRed)
		elif lossFnName == "bcel":
			lossFunc = torch.nn.BCEWithLogitsLoss(reduction=lossRed)
		elif lossFnName == "sm":
			lossFunc = torch.nn.SoftMarginLoss(reduction=lossRed)
		elif lossFnName == "mlsm":
			lossFunc = torch.nn.MultiLabelSoftMarginLoss(reduction=lossRed)
		else:
			exitWithMsg("invalid loss function name " + lossFnName)
		return lossFunc

	@staticmethod
	def createOptimizer(model, optName):
		"""
		create optimizer
		"""
		config = model.config
		learnRate = config.getFloatConfig("train.opt.learning.rate")[0]
		weightDecay = config.getFloatConfig("train.opt.weight.decay")[0]
		momentum = config.getFloatConfig("train.opt.momentum")[0]
		eps = config.getFloatConfig("train.opt.eps")[0]
		if optName == "sgd":
			dampening = config.getFloatConfig("train.opt.dampening")[0]
			momentumNesterov = config.getBooleanConfig("train.opt.momentum.nesterov")[0]
			optimizer = torch.optim.SGD(model.parameters(),lr=learnRate, momentum=momentum, 
			dampening=dampening, weight_decay=weightDecay, nesterov=momentumNesterov)
		elif optName == "adam":
		   	betas = config.getFloatListConfig("train.opt.betas")[0]
		   	betas = (betas[0], betas[1]) 
		   	optimizer = torch.optim.Adam(model.parameters(), lr=learnRate,betas=betas, eps = eps,
    		weight_decay=weightDecay)
		elif optName == "rmsprop":
			alpha = config.getFloatConfig("train.opt.alpha")[0]
			optimizer = torch.optim.RMSprop(model.parameters(), lr=learnRate, alpha=alpha,
			eps=eps, weight_decay=weightDecay, momentum=momentum)
		else:
			exitWithMsg("invalid optimizer name " + optName)
		return optimizer


	def forward(self, x):
		"""
    	In the forward function we accept a Tensor of input data and we must return
    	a Tensor of output data. We can use Modules defined in the constructor as
    	well as arbitrary (differentiable) operations on Tensors.
		"""
		y = self.layers(x)	
		return y

	@staticmethod
	def prepData(model, dataSource, includeOutFld=True):
		"""
		loads and prepares  data
		"""
		# parameters
		fieldIndices = model.config.getIntListConfig("train.data.fields")[0]
		featFieldIndices = model.config.getIntListConfig("train.data.feature.fields")[0]

		#all data and feature data
		isDataFile = isinstance(dataSource, str)
		selFieldIndices = fieldIndices if includeOutFld else fieldIndices[:-1]
		if isDataFile: 
			#source file path 
			(data, featData) = loadDataFile(dataSource, ",", selFieldIndices, featFieldIndices)
		else:
			# tabular data
			data = tableSelFieldsFilter(dataSource, selFieldIndices)
			featData = tableSelFieldsFilter(data, featFieldIndices)
			featData = np.array(featData)
			
		if (model.config.getStringConfig("common.preprocessing")[0] == "scale"):
		    scalingMethod = model.config.getStringConfig("common.scaling.method")[0]
		    featData = scaleData(featData, scalingMethod)
		
		# target data
		if includeOutFld:
			outFieldIndices = model.config.getStringConfig("train.data.out.fields")[0]
			outFieldIndices = strToIntArray(outFieldIndices, ",")
			if isDataFile:
				outData = data[:,outFieldIndices]
			else:
				outData = tableSelFieldsFilter(data, outFieldIndices)
				outData = np.array(outData)
			foData = (featData.astype(np.float32), outData.astype(np.float32))
		else:
			foData = featData.astype(np.float32)
		return foData

	@staticmethod
	def saveCheckpt(model):
		"""
		checkpoints model
		"""
		print("..saving model checkpoint")
		modelDirectory = model.config.getStringConfig("common.model.directory")[0]
		assert os.path.exists(modelDirectory), "model save directory does not exist"
		modelFile = model.config.getStringConfig("common.model.file")[0]
		filepath = os.path.join(modelDirectory, modelFile)
		state = {"state_dict": model.state_dict(), "optim_dict": model.optimizer.state_dict()}
		torch.save(state, filepath)
		if model.verbose:
			print("model saved")

	@staticmethod
	def restoreCheckpt(model, loadOpt=False):
		"""
		restored checkpointed model
		"""
		print("..restoring model checkpoint")
		modelDirectory = model.config.getStringConfig("common.model.directory")[0]
		modelFile = model.config.getStringConfig("common.model.file")[0]
		filepath = os.path.join(modelDirectory, modelFile)
		assert os.path.exists(filepath), "model save file does not exist"
		checkpoint = torch.load(filepath)
		model.load_state_dict(checkpoint["state_dict"])
		if loadOpt:
			model.optimizer.load_state_dict(checkpoint["optim_dict"])

	@staticmethod
	def processClassifOutput(yPred, config):
		"""
		extracts probability label 1 or label with highest probability
		"""
		outType = config.getStringConfig("predict.output")[0]
		if outType == "prob":
			yPred = yPred[:, 1]
			yPred = list(map(lambda v : "{:.3f}".format(v), yPred))
		else:
			yPred = np.argmax(yPred, axis=1)
		return yPred
		
	@staticmethod
	def printPrediction(yPred, config, dataSource):
		"""
		prints input feature data and prediction
		"""
		#prDataFilePath = config.getStringConfig("predict.data.file")[0]
		padWidth = config.getIntConfig("predict.feat.pad.size")[0]
		i = 0
		if type(dataSource) == str:
			for rec in fileRecGen(dataSource, ","):
				feat = (",".join(rec)).ljust(padWidth, " ")
				rec = feat + "\t" + str(yPred[i])
				print(rec)
				i += 1
		else:
			for rec in dataSource:
				srec = toStrList(rec, 6)
				feat = (",".join(srec)).ljust(padWidth, " ")
				srec = feat + "\t" + str(yPred[i])
				print(srec)
				i += 1
			
			
	@staticmethod
	def allTrain(model):
		"""
		train with all data
		"""
		# train mode
		model.train()
		for t in range(model.numIter):

	
			# Forward pass: Compute predicted y by passing x to the model
			yPred = model(model.featData)

			# Compute and print loss
			loss = model.lossFn(yPred, model.outData)
			if model.verbose and  t % 50 == 0:
				print("epoch {}  loss {:.6f}".format(t, loss.item()))

			# Zero gradients, perform a backward pass, and update the weights.
			model.optimizer.zero_grad()
			loss.backward()
			model.optimizer.step()    	

		#validate
		model.eval()
		yPred = model(model.validFeatData)
		yPred = yPred.data.cpu().numpy()
		yActual = model.validOutData
		if model.verbose:
			result = np.concatenate((yPred, yActual), axis = 1)
			print("predicted  actual")
			print(result)
		
		score = perfMetric(model.accMetric, yActual, yPred)
		print(formatFloat(3, score, "perf score"))
		return score

	@staticmethod
	def batchTrain(model):
		"""
		train with batch data
		"""
		trainData = TensorDataset(model.featData, model.outData)
		trainDataLoader = DataLoader(dataset=trainData, batch_size=model.batchSize, shuffle=True)
		epochIntv = model.config.getIntConfig("train.epoch.intv")[0]

		# train mode
		model.train()
 
		if model.trackErr:
			trErr = list()
			vaErr = list()
		#epoch
		for t in range(model.numIter):
			#batch
			b = 0
			epochLoss = 0.0
			for xBatch, yBatch in trainDataLoader:
	
				# Forward pass: Compute predicted y by passing x to the model
				yPred = model(xBatch)
				
				# Compute and print loss
				loss = model.lossFn(yPred, yBatch)
				if model.verbose and t % epochIntv == 0 and b % model.batchIntv == 0:
					print("epoch {}  batch {}  loss {:.6f}".format(t, b, loss.item()))
				
				if model.trackErr and model.batchIntv == 0:
					epochLoss += loss.item()
				
				#error tracking at batch level
				if model.trackErr and model.batchIntv > 0 and b % model.batchIntv == 0:
					trErr.append(loss.item())
					vloss = FeedForwardNetwork.evaluateModel(model)
					vaErr.append(vloss)

				# Zero gradients, perform a backward pass, and update the weights.
				model.optimizer.zero_grad()
				loss.backward()
				model.optimizer.step()    	
				b += 1
			
			#error tracking at epoch level
			if model.trackErr and model.batchIntv == 0:
				epochLoss /= len(trainDataLoader)
				trErr.append(epochLoss)
				vloss = FeedForwardNetwork.evaluateModel(model)
				vaErr.append(vloss)
			
		#validate
		model.eval()
		yPred = model(model.validFeatData)
		yPred = yPred.data.cpu().numpy()
		yActual = model.validOutData
		if model.verbose:
			vsize = yPred.shape[0]
			print("\npredicted \t\t actual")
			for i in range(vsize):
				print(str(yPred[i]) + "\t" + str(yActual[i]))
		
		score = perfMetric(model.accMetric, yActual, yPred)
		print(yActual)
		print(yPred)
		print(formatFloat(3, score, "perf score"))

		#save
		modelSave = model.config.getBooleanConfig("train.model.save")[0]
		if modelSave:
			FeedForwardNetwork.saveCheckpt(model)

		if model.trackErr:
			x = np.arange(len(trErr))
			plt.plot(x,trErr,label = "training error")
			plt.plot(x,vaErr,label = "validation error")
			plt.xlabel("iteration")
			plt.ylabel("error")
			plt.legend(["training error", "validation error"], loc='upper left')
			plt.show()
		
		if model.config.getBooleanConfig("train.print.weights")[0]:
			print("model weights")
			for param in model.parameters():
				print(param.data)
		return score

	@staticmethod
	def predict(model, dataSource = None):
		"""
		predict
		"""
		#train or restore model
		useSavedModel = model.config.getBooleanConfig("predict.use.saved.model")[0]
		if useSavedModel:
			FeedForwardNetwork.restoreCheckpt(model)
		else:
			FeedForwardNetwork.batchTrain(model) 

		#predict
		if dataSource is None:
			dataSource = model.config.getStringConfig("predict.data.file")[0]
		featData  = FeedForwardNetwork.prepData(model, dataSource, False)
		featData = torch.from_numpy(featData)
		model.eval()
		yPred = model(featData)
		yPred = yPred.data.cpu().numpy()
		
		if model.outputSize == 2:
			#classification
			yPred = FeedForwardNetwork.processClassifOutput(yPred, model.config)
			
		# print prediction
		if model.config.getBooleanConfig("predict.print.output")[0]:
			FeedForwardNetwork.printPrediction(yPred, model.config, dataSource)
		
		return yPred

	@staticmethod
	def evaluateModel(model):
		"""
		evaluate model
		"""
		model.eval()
		with torch.no_grad():
			yPred = model(model.validFeatData)
			yPred = yPred.data.cpu().numpy()
			yActual = model.validOutData
			score = perfMetric(model.lossFnStr, yActual, yPred)
		model.train()
		return score
    	
	@staticmethod
	def prepValidate(model, dataSource=None):
		"""
		prepare for validation
		"""
		#train or restore model
		if not model.restored:
			useSavedModel = model.config.getBooleanConfig("predict.use.saved.model")[0]
			if useSavedModel:
				FeedForwardNetwork.restoreCheckpt(model)
			else:
				FeedForwardNetwork.batchTrain(model)
			model.restored = True
			
		if 	dataSource is not None:
			model.setValidationData(dataSource)
 
	@staticmethod
	def validateModel(model):
		"""
		pmodel validation
		"""
		model.eval()
		yPred = model(model.validFeatData)
		yPred = yPred.data.cpu().numpy()
		model.yPred = yPred
		yActual = model.validOutData
		if model.verbose:
			vsize = yPred.shape[0]
			print("\npredicted \t actual")
			for i in range(vsize):
				print("{:.3f}\t\t{:.3f}".format(yPred[i][0], yActual[i][0]))
			
		score = perfMetric(model.accMetric, yActual, yPred)
		print(formatFloat(3, score, "perf score"))
		return score
 		
	@staticmethod
	def calibrateModel(model):
		"""
		pmodel calibration
		"""
		FeedForwardNetwork.prepValidate(model)
		FeedForwardNetwork.validateModel(model)
		
		yPred = model.yPred.flatten()
		yActual = model.validOutData.flatten()
		nsamp = len(yActual)
		
		#print(yPred.shape)
		#print(yActual.shape)
		
		nBins = model.config.getIntConfig("calibrate.num.bins")[0]
		prThreshhold = model.config.getFloatConfig("calibrate.pred.prob.thresh")[0]
		
		minConf = yPred.min()
		maxConf = yPred.max()
		bsize = (maxConf - minConf) / nBins
		#print("minConf {:.3f}  maxConf {:.3f}  bsize {:.3f}".format(minConf, maxConf, bsize))
		blist = list(map(lambda i : None, range(nBins)))
		
		#binning
		for yp, ya in zip(yPred, yActual):
			indx = int((yp - minConf) / bsize)
			if indx == nBins:
				indx = nBins - 1
			#print("yp {:.3f}  indx {}".format(yp, indx))
			pair = (yp, ya)
			plist  = blist[indx]
			if plist is None:
				plist = list()
				blist[indx] = plist 
			plist.append(pair)
		 
		x = list()
		y = list()
		yideal = list()
		ece = 0
		mce = 0
		
		# per bin confidence and accuracy
		for plist in blist:
			ypl = list(map(lambda p : p[0], plist))
			ypm = statistics.mean(ypl)
			x.append(ypm)
			
			ypcount = 0
			for p in plist:
				yp = 1 if p[0] > prThreshhold else 0
				if (yp == 1 and p[1] == 1):
					ypcount += 1
				 
			acc = ypcount / len(plist)
			y.append(acc)
			yideal.append(ypm)
			
			ce = abs(ypm - acc)
			ece += len(plist) * ce
			if ce > mce:
				mce = ce
		
		#calibration plot	
		drawPairPlot(x, y, yideal, "confidence", "accuracy", "actual", "ideal")
		
		#expected calibration error
		ece /= nsamp
		print("expected calibration error\t{:.3f}".format(ece))
		print("maximum calibration error\t{:.3f}".format(mce))
				
			
	@staticmethod
	def calibrateModelLocal(model):
		"""
		pmodel calibration based k nearest neghbors
		"""
		FeedForwardNetwork.prepValidate(model)
		FeedForwardNetwork.validateModel(model)
		
		yPred = model.yPred.flatten()
		yActual = model.validOutData.flatten()
		nsamp = len(yActual)
		
		neighborCnt =  model.config.getIntConfig("calibrate.num.nearest.neighbors")[0]
		prThreshhold = model.config.getFloatConfig("calibrate.pred.prob.thresh")[0]
		fData = model.validFeatData.numpy()
		tree = KDTree(fData, leaf_size=4)
		
		dist, ind = tree.query(fData, k=neighborCnt)
		calibs = list()
		#all data
		for si, ni in enumerate(ind):
			conf = 0
			ypcount = 0
			#all neighbors
			for i in ni:
				conf += yPred[i]
				yp = 1 if yPred[i] > prThreshhold else 0
				if (yp == 1 and yActual[i] == 1):
					ypcount += 1
			conf /= neighborCnt
			acc = ypcount / neighborCnt
			calib = (si, conf, acc)
			calibs.append(calib)
			
		#descending sort by difference between confidence and accuracy
		calibs = sorted(calibs, key=lambda c : abs(c[1] - c[2]), reverse=True)
		print("local calibration")
		print("conf\taccu\trecord")
		for i in range(19):
			si, conf, acc = calibs[i]
			rec = toStrFromList(fData[si], 3)
			print("{:.3f}\t{:.3f}\t{}".format(conf, acc, rec))
		
		
	
		
   	