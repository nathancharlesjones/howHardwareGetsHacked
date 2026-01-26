#include "config.h"

void main(int argc, char ** argv)
{
    OBJ_T *obj = OBJ_INSTANCE(argc, argv);
    OBJ_INIT(obj);
    while(1) OBJ_TICK(obj);
}