#include <stdlib.h>
#include "fob_testing.h"

#if !BUILD_TEST
#error "Testing file included in non-test build"
#endif

fob_t* fob_new(void) {
    return calloc(1, sizeof(fob_t));
}

void fob_free(fob_t* c) {
    free(c);
}
