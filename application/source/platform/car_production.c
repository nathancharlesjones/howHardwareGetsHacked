#include "car_production.h"

static car_t s_car;

car_t* car_instance(void)
{
    return &s_car;
}