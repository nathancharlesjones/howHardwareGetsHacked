#******************************************************************************
#
# Makefile - Rules for building the driver library.
#
# Copyright (c) 2005-2020 Texas Instruments Incorporated.  All rights reserved.
# Software License Agreement
# 
#   Redistribution and use in source and binary forms, with or without
#   modification, are permitted provided that the following conditions
#   are met:
# 
#   Redistributions of source code must retain the above copyright
#   notice, this list of conditions and the following disclaimer.
# 
#   Redistributions in binary form must reproduce the above copyright
#   notice, this list of conditions and the following disclaimer in the
#   documentation and/or other materials provided with the  
#   distribution.
# 
#   Neither the name of Texas Instruments Incorporated nor the names of
#   its contributors may be used to endorse or promote products derived
#   from this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# 
# This is part of revision 2.2.0.295 of the Tiva Peripheral Driver Library.
#
#******************************************************************************

#
# The base directory for TivaWare.
#
ROOT=..

#
# Include the common make definitions.
#
include ${ROOT}/makedefs

#
# Where to find header files that do not live in the source directory.
#
IPATH=..

#
# The default rule, which causes the driver library to be built.
#
all: ${BUILD_DIR}
all: ${BUILD_DIR}/libdriver.a

#
# The rule to clean out all the build products.
#
clean:
	@rm -rf ${BUILD_DIR} ${wildcard *~}

#
# The rule to create the target directory.
#
${BUILD_DIR}:
	@mkdir -p ${BUILD_DIR}

#
# Rules for building the driver library.
#
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/adc.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/aes.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/can.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/comp.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/cpu.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/crc.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/des.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/eeprom.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/emac.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/epi.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/flash.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/fpu.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/gpio.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/hibernate.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/i2c.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/interrupt.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/lcd.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/mpu.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/onewire.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/pwm.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/qei.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/shamd5.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/ssi.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/sw_crc.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/sysctl.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/sysexc.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/systick.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/timer.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/uart.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/udma.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/usb.o
${BUILD_DIR}/libdriver.a: ${BUILD_DIR}/watchdog.o

#
# Include the automatically generated dependency files.
#
ifneq (${MAKECMDGOALS},clean)
-include ${wildcard ${BUILD_DIR}/*.d} __dummy__
endif
