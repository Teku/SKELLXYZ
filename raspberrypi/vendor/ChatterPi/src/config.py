#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May 18 14:01:47 2020

@author: Mike McGurrin
"""
from configparser import ConfigParser
# Initialize constants from config.ini
cfg = ConfigParser()
def update():
	global SERVO_MIN
	global SERVO_MAX
	global TRAVEL
	global MIN_ANGLE
	global MAX_ANGLE
	global STYLE
	global THRESHOLD
	global LEVEL1
	global LEVEL2
	global LEVEL3
	global FIlTERED_LEVEL1
	global FIlTERED_LEVEL2
	global FIlTERED_LEVEL3
	global BUFFER_SIZE
	global SOURCE
	global MIC_TIME
	global OUTPUT_CHANNELS
	global AMBIENT
	global PROP_TRIGGER
	global DELAY
	global JAW_ENABLED
	global JAW_PIN

	cfg.read('config.ini')

	SERVO_MIN = int(cfg['SERVO']['SERVO_MIN'])
	SERVO_MAX = int(cfg['SERVO']['SERVO_MAX'])
	TRAVEL = int(cfg['SERVO']['TRAVEL'])
	MIN_ANGLE = int(cfg['SERVO']['MIN_ANGLE'])
	MAX_ANGLE = int(cfg['SERVO']['MAX_ANGLE'])
	STYLE = int(cfg['CONTROLLER']['STYLE'])
	THRESHOLD = int(cfg['CONTROLLER']['THRESHOLD'])
	LEVEL1 = int(cfg['CONTROLLER']['LEVEL1'])
	LEVEL2 = int(cfg['CONTROLLER']['LEVEL2'])
	LEVEL3 = int(cfg['CONTROLLER']['LEVEL3'])
	FIlTERED_LEVEL1 = int(cfg['CONTROLLER']['FIlTERED_LEVEL1'])
	FIlTERED_LEVEL2 = int(cfg['CONTROLLER']['FIlTERED_LEVEL2'])
	FIlTERED_LEVEL3 = int(cfg['CONTROLLER']['FIlTERED_LEVEL3'])
	BUFFER_SIZE = int(cfg['AUDIO']['BUFFER_SIZE']) 
	SOURCE = cfg['AUDIO']['SOURCE']
	MIC_TIME = int(cfg['AUDIO']['MIC_TIME'])
	OUTPUT_CHANNELS = cfg['AUDIO']['OUTPUT_CHANNELS']
	AMBIENT = cfg['AUDIO']['AMBIENT']
	PROP_TRIGGER = cfg['PROP']['PROP_TRIGGER']
	DELAY = int(cfg['PROP']['DELAY'])
	JAW_ENABLED = cfg['PROP']['JAW_ENABLED']
	JAW_PIN = int(cfg['PINS']['JAW_PIN'])

