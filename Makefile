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
