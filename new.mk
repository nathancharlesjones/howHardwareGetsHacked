# ===============================
# Top-level firmware dispatcher
# ===============================

PLATFORM ?=
ROLE     ?=

# Discover all available platforms by looking in hardware/
AVAILABLE_PLATFORMS := $(filter-out include,$(patsubst hardware/%,%,$(wildcard hardware/*)))
AVAILABLE_ROLES := car paired_fob unpaired_fob

# Default target: build all platforms and roles
ifeq ($(PLATFORM)$(ROLE),)
.PHONY: all
all:
	@echo "Building all platforms and roles..."
	@$(foreach plat,$(AVAILABLE_PLATFORMS), \
		$(foreach role,$(AVAILABLE_ROLES), \
			echo "=== Building $(plat) $(role) ===" && \
			$(MAKE) --no-print-directory PLATFORM=$(plat) ROLE=$(role) build_single || exit 1; \
		) \
	)
else
# If either PLATFORM or ROLE is set, both must be set
ifeq ($(PLATFORM),)
$(error ROLE is set to "$(ROLE)" but PLATFORM is not set. Valid platforms: $(AVAILABLE_PLATFORMS))
endif

ifeq ($(ROLE),)
$(error PLATFORM is set to "$(PLATFORM)" but ROLE is not set. Valid roles: $(AVAILABLE_ROLES))
endif

# Validate the specified platform exists
ifeq ($(filter $(PLATFORM),$(AVAILABLE_PLATFORMS)),)
$(error Unknown PLATFORM "$(PLATFORM)". Available platforms: $(AVAILABLE_PLATFORMS))
endif

# Validate the specified role is valid
ifeq ($(filter $(ROLE),$(AVAILABLE_ROLES)),)
$(error Unknown ROLE "$(ROLE)". Available roles: $(AVAILABLE_ROLES))
endif

# Add feature flags for car builds
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

export PLATFORM ROLE C_DEFS

.PHONY: all build_single
all: build_single

build_single:
	@echo "Building $(PLATFORM) $(ROLE)..."
	$(MAKE) -C hardware/$(PLATFORM)

endif

# Clean target
.PHONY: clean
clean:
ifeq ($(PLATFORM),)
	@echo "Cleaning all platforms..."
	@$(foreach plat,$(AVAILABLE_PLATFORMS), \
		echo "Cleaning $(plat)..." && \
		$(MAKE) -C hardware/$(plat) clean || exit 1; \
	)
else
	@echo "Cleaning $(PLATFORM)..."
	$(MAKE) -C hardware/$(PLATFORM) clean
endif