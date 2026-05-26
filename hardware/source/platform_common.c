#include "platform.h"
#include "platform_impl.h"
#include "dataFormats.h"

void loadFobState(FOB_FLASH_DATA *data) {
    load_flash((void*)data, sizeof(FOB_FLASH_DATA));
}

void saveFobState(const FOB_FLASH_DATA *data) {
    save_flash((const void*)data, sizeof(FOB_FLASH_DATA));
}

void loadCarState(CAR_FLASH_DATA *data) {
    load_flash((void*)data, sizeof(CAR_FLASH_DATA));
}

void saveCarState(const CAR_FLASH_DATA *data) {
    save_flash((const void*)data, sizeof(CAR_FLASH_DATA));
}