#ifndef CAR_H
#define CAR_H

typedef struct car car_t;

void car_init(car_t* c, int argc, char ** argv);
void car_tick(car_t* c);

#endif // CAR_H