#ifndef GPIO_EEPROM_FLASH_H
#define GPIO_EEPROM_FLASH_H

// GPIO setup
/* Ex:
GPIOPinTypeGPIOInput(GPIO_PORTF_BASE, GPIO_PIN_4);
GPIOPadConfigSet(GPIO_PORTF_BASE, GPIO_PIN_4, GPIO_STRENGTH_4MA,
                   GPIO_PIN_TYPE_STD_WPU);
*/

// GPIO write
/* Ex:
GPIOPinWrite(GPIO_PORTF_BASE, GPIO_PIN_1, GPIO_PIN_1);
*/

// GPIO read
/* Ex:
GPIOPinRead(GPIO_PORTF_BASE, GPIO_PIN_4);
*/

// EEPROM init
/* Ex:
EEPROMInit();
*/

// EEPROM read
/* Ex:
EEPROMRead((uint32_t *)eeprom_message, UNLOCK_EEPROM_LOC,
               UNLOCK_EEPROM_SIZE);
*/

// EEPROM write (just in case? not used by insecure example)


// Flash erase
/* Ex:
FlashErase(FOB_STATE_PTR);
*/

// Flash program
/* Ex:
FlashProgram((uint32_t *)flash_data, FOB_STATE_PTR, FLASH_DATA_SIZE);
*/

#endif // GPIO_EEPROM_FLASH_H