#include <stdlib.h>
#include "car_testing.h"

#if !BUILD_TEST
#error "Testing file included in non-test build"
#endif

car_t* car_new(void) {
    return calloc(1, sizeof(car_t));
}

void car_free(car_t* c) {
    free(c);
}
