#  2023 eCTF
#  Car Makefile
#  Kyle Scaplen
#
#  (c) 2023 The MITRE Corporation
#
# This source file is part of an example system for MITRE's 2023 Embedded System CTF (eCTF).
# This code is being provided only for educational purposes for the 2023 MITRE eCTF competition,
# and may not meet MITRE standards for quality. Use this code at your own risk!

# define the part type and base directory - must be defined for makedefs to work
PART=TM4C123GH6PM
CFLAGSgcc=-DTARGET_IS_TM4C123_RB1
ROOT=.

# Uncomment to enable debug symbols
DEBUG=1

# additional base directories
TIVA_ROOT=${ROOT}/libraries/tivaware

#ROLE ?=
ifeq ($(ROLE),car)
FIRMWARE_OBJ := carFirmware.o
else ifeq ($(ROLE),paired_fob)
FIRMWARE_OBJ := fobFirmware.o
else ifeq ($(ROLE),unpaired_fob)
FIRMWARE_OBJ := fobFirmware.o
else
$(error ROLE not set correctly)
endif

BUILD_DIR = build/$(ROLE)

# add additional directories to search for source files to VPATH
VPATH=${ROOT}/source
VPATH+=$(ROOT)/../../application/source
VPATH+=${TIVA_ROOT}

# add additional directories to search for header files to IPATH
IPATH=${ROOT}/../include
IPATH+=$(ROOT)/../../application/include
IPATH+=$(BUILD_DIR)
IPATH+=${TIVA_ROOT}

# Include common makedefs
include ${TIVA_ROOT}/makedefs
include ../../secrets/secrets.mk

########################################################
############### START car customization ################

# Optimizations
CFLAGS+=-Os

.DEFAULT_GOAL := all
all: $(BUILD_DIR) $(SECRETS_HDR) $(BUILD_DIR)/firmware.axf copy_artifacts


# build libraries
${TIVA_ROOT}/driverlib/build/libdriver.a:
	${MAKE} -C ${TIVA_ROOT}/driverlib BUILD_DIR=build

tivaware: ${TIVA_ROOT}/driverlib/build/libdriver.a

# clean the libraries
clean_tivaware:
	${MAKE} -C ${TIVA_ROOT}/driverlib clean BUILD_DIR=build

# clean all build products
clean: clean_tivaware
	@rm -rf build ${wildcard *~}

# create the output directory
${BUILD_DIR}:
	@mkdir -p ${BUILD_DIR}


${BUILD_DIR}/firmware.axf: ${BUILD_DIR}/uart_tm4c.o
${BUILD_DIR}/firmware.axf: ${BUILD_DIR}/messages.o
${BUILD_DIR}/firmware.axf: ${BUILD_DIR}/${FIRMWARE_OBJ}
${BUILD_DIR}/firmware.axf: ${BUILD_DIR}/tm4c.o
${BUILD_DIR}/firmware.axf: ${BUILD_DIR}/startup_${COMPILER}.o
${BUILD_DIR}/firmware.axf: ${TIVA_ROOT}/driverlib/build/libdriver.a

copy_artifacts:
	# cp ${COMPILER}/firmware.bin ${BIN_PATH}
	# cp ${COMPILER}/firmware.axf ${ELF_PATH}
	cp ${SECRETS_DIR}/global_secrets.txt ${BUILD_DIR}

SCATTERgcc_firmware=${TIVA_ROOT}/firmware.ld
ENTRY_firmware=Firmware_Startup

# Include the automatically generated dependency files.
ifneq (${MAKECMDGOALS},clean)
-include ${wildcard ${BUILD_DIR}/*.d} __dummy__
endif