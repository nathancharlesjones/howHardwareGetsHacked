# ===============================
# secrets.mk – shared logic
# ===============================

SECRETS_DIR ?= ../../secrets
SECRETS_HDR := $(BUILD_DIR)/secrets.h

ifeq ($(ROLE),car)
GEN_SECRET_CMD = \
	python3 ../../application/car_gen_secret.py \
	  --car-id $(CAR_ID) \
	  --secret-file $(SECRETS_DIR)/car_secrets.json \
	  --header-file $(SECRETS_HDR)

else ifeq ($(ROLE),paired_fob)
GEN_SECRET_CMD = \
	python3 ../../application/fob_gen_secret.py \
	  --car-id $(CAR_ID) \
	  --pair-pin $(PAIR_PIN) \
	  --secret-file $(SECRETS_DIR)/car_secrets.json \
	  --header-file $(SECRETS_HDR) \
	  --paired

else ifeq ($(ROLE),unpaired_fob)
GEN_SECRET_CMD = \
	python3 ../../application/fob_gen_secret.py \
	  --header-file $(SECRETS_HDR)
endif

$(SECRETS_HDR):
	@echo "Generating secrets for $(ROLE)"
	$(GEN_SECRET_CMD)