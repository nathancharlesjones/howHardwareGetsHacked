#include "fob_production.h"

static fob_t s_fob;

fob_t* fob_instance(void)
{
    return &s_fob;
}