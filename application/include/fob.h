#ifndef FOB_H
#define FOB_H

typedef struct fob fob_t;

void fob_init(fob_t* c, int argc, char ** argv);
void fob_tick(fob_t* c);

#endif // FOB_H