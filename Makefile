# ===============================
# Top-level firmware dispatcher
# ===============================

PLATFORM ?=
ROLE     ?=

ifeq ($(PLATFORM),)
$(error PLATFORM not set: tm4c or stm32)
endif

ifeq ($(ROLE),)
$(error ROLE not set: car, paired_fob, or unpaired_fob)
endif

ifeq ($(ROLE),car)
	ifdef UNLOCK_FLAG
	C_DEFS += -DUNLOCK_FLAG=\"$(UNLOCK_FLAG)\"
	endif

	ifdef FEATURE1_FLAG
	C_DEFS += -DFEATURE1_FLAG=\"$(FEATURE1_FLAG)\"
	endif

	ifdef FEATURE2_FLAG
	C_DEFS += -DFEATURE2_FLAG=\"$(FEATURE2_FLAG)\"
	endif

	ifdef FEATURE3_FLAG
	C_DEFS += -DFEATURE3_FLAG=\"$(FEATURE3_FLAG)\"
	endif
endif

export PLATFORM ROLE

ifeq ($(PLATFORM),tm4c)
SUBDIR := tm4c
else ifeq ($(PLATFORM),stm32)
SUBDIR := stm32
else
$(error Unknown PLATFORM $(PLATFORM))
endif

.PHONY: all clean
all:
	$(MAKE) -C hardware/$(SUBDIR)

clean:
	$(MAKE) -C hardware/$(SUBDIR) clean
