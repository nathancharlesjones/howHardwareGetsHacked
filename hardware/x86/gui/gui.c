/**
 * @file gui.c
 * @brief GUI implementation using microui + SDL2
 * 
 * Provides the simulation GUI:
 * - LED indicator (colored rectangle)
 * - Button (clickable)
 * - Serial port status display
 * - Board UART reconnection dropdown
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <sys/stat.h>

#include <SDL2/SDL.h>
#include "microui.h"
#include "gui.h"
#include "platform.h"

/* Forward declaration for uart functions used by GUI */
extern const char* uart_get_board_path(void);
extern const char* uart_get_host_path(void);
extern bool uart_reconnect_board(const char* new_path);

/*******************************************************************************
 * Configuration
 ******************************************************************************/
#define WINDOW_WIDTH  400
#define WINDOW_HEIGHT 300

/* Colors for LED display */
static const SDL_Color led_colors[] = {
    [OFF]   = { 64, 64, 64, 255 },      /* Dark gray */
    [RED]   = { 255, 0, 0, 255 },       /* Red */
    [GREEN] = { 0, 255, 0, 255 },       /* Green */
    [WHITE] = { 255, 255, 255, 255 }    /* White */
};

/*******************************************************************************
 * File-local variables
 ******************************************************************************/
static SDL_Window* window = NULL;
static SDL_Renderer* renderer = NULL;
static mu_Context* ctx = NULL;

/* Atlas texture for microui font rendering */
static SDL_Texture* atlas_texture = NULL;

/* microui atlas - embedded 8x8 font */
#include "atlas.inl"

/*******************************************************************************
 * microui renderer backend
 ******************************************************************************/
static int text_width(mu_Font font, const char* text, int len)
{
    (void)font;
    if (len < 0) len = strlen(text);
    return len * 8;  /* 8 pixels per character */
}

static int text_height(mu_Font font)
{
    (void)font;
    return 14;  /* Line height */
}

static void render_texture(SDL_Rect src, SDL_Rect dst, SDL_Color color)
{
    SDL_SetTextureColorMod(atlas_texture, color.r, color.g, color.b);
    SDL_SetTextureAlphaMod(atlas_texture, color.a);
    SDL_RenderCopy(renderer, atlas_texture, &src, &dst);
}

static void render_microui(void)
{
    mu_Command* cmd = NULL;
    
    while (mu_next_command(ctx, &cmd)) {
        switch (cmd->type) {
            case MU_COMMAND_TEXT: {
                SDL_Color c = {
                    cmd->text.color.r,
                    cmd->text.color.g,
                    cmd->text.color.b,
                    cmd->text.color.a
                };
                const char* p = cmd->text.str;
                int x = cmd->text.pos.x;
                int y = cmd->text.pos.y;
                while (*p) {
                    int char_idx = *p - 32;
                    if (char_idx < 0 || char_idx >= 96) char_idx = 0;
                    
                    /* Calculate source position in atlas grid */
                    int src_x = (char_idx % FONT_CHARS_PER_ROW) * FONT_CHAR_WIDTH;
                    int src_y = FONT_START_Y + (char_idx / FONT_CHARS_PER_ROW) * FONT_CHAR_HEIGHT;
                    
                    SDL_Rect src = { src_x, src_y, FONT_CHAR_WIDTH, FONT_CHAR_HEIGHT };
                    SDL_Rect dst = { x, y, FONT_CHAR_WIDTH, FONT_CHAR_HEIGHT };
                    render_texture(src, dst, c);
                    x += FONT_CHAR_WIDTH;
                    p++;
                }
                break;
            }
            case MU_COMMAND_RECT: {
                SDL_SetRenderDrawColor(renderer,
                    cmd->rect.color.r,
                    cmd->rect.color.g,
                    cmd->rect.color.b,
                    cmd->rect.color.a);
                SDL_Rect r = {
                    cmd->rect.rect.x,
                    cmd->rect.rect.y,
                    cmd->rect.rect.w,
                    cmd->rect.rect.h
                };
                SDL_RenderFillRect(renderer, &r);
                break;
            }
            case MU_COMMAND_ICON: {
                SDL_Color c = {
                    cmd->icon.color.r,
                    cmd->icon.color.g,
                    cmd->icon.color.b,
                    cmd->icon.color.a
                };
                int id = cmd->icon.id;
                SDL_Rect src = { id * 18, 0, 18, 18 };
                int x = cmd->icon.rect.x + (cmd->icon.rect.w - 18) / 2;
                int y = cmd->icon.rect.y + (cmd->icon.rect.h - 18) / 2;
                SDL_Rect dst = { x, y, 18, 18 };
                render_texture(src, dst, c);
                break;
            }
            case MU_COMMAND_CLIP: {
                SDL_Rect r = {
                    cmd->clip.rect.x,
                    cmd->clip.rect.y,
                    cmd->clip.rect.w,
                    cmd->clip.rect.h
                };
                SDL_RenderSetClipRect(renderer, &r);
                break;
            }
        }
    }
}

static int map_sdl_button(int button)
{
    switch (button) {
        case SDL_BUTTON_LEFT:   return MU_MOUSE_LEFT;
        case SDL_BUTTON_RIGHT:  return MU_MOUSE_RIGHT;
        case SDL_BUTTON_MIDDLE: return MU_MOUSE_MIDDLE;
        default: return 0;
    }
}

static int map_sdl_key(int key)
{
    switch (key) {
        case SDLK_LSHIFT:
        case SDLK_RSHIFT:    return MU_KEY_SHIFT;
        case SDLK_LCTRL:
        case SDLK_RCTRL:     return MU_KEY_CTRL;
        case SDLK_LALT:
        case SDLK_RALT:      return MU_KEY_ALT;
        case SDLK_RETURN:    return MU_KEY_RETURN;
        case SDLK_BACKSPACE: return MU_KEY_BACKSPACE;
        default: return 0;
    }
}

/*******************************************************************************
 * GUI API Implementation
 ******************************************************************************/
bool gui_init(const char* title)
{
    /* Initialize SDL */
    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        fprintf(stderr, "SDL_Init failed: %s\n", SDL_GetError());
        return false;
    }
    
    /* Create window */
    window = SDL_CreateWindow(
        title ? title : "Simulation",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        WINDOW_WIDTH, WINDOW_HEIGHT,
        SDL_WINDOW_SHOWN
    );
    if (!window) {
        fprintf(stderr, "SDL_CreateWindow failed: %s\n", SDL_GetError());
        SDL_Quit();
        return false;
    }
    
    /* Create renderer */
    renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED);
    if (!renderer) {
        fprintf(stderr, "SDL_CreateRenderer failed: %s\n", SDL_GetError());
        SDL_DestroyWindow(window);
        SDL_Quit();
        return false;
    }
    
    /* Enable alpha blending */
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    
    /* Create atlas texture */
    atlas_texture = SDL_CreateTexture(
        renderer,
        SDL_PIXELFORMAT_RGBA32,
        SDL_TEXTUREACCESS_STATIC,
        ATLAS_WIDTH, ATLAS_HEIGHT
    );
    if (!atlas_texture) {
        fprintf(stderr, "Failed to create atlas texture\n");
        SDL_DestroyRenderer(renderer);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return false;
    }
    
    SDL_UpdateTexture(atlas_texture, NULL, atlas_data, ATLAS_WIDTH * 4);
    SDL_SetTextureBlendMode(atlas_texture, SDL_BLENDMODE_BLEND);
    
    /* Initialize microui */
    ctx = malloc(sizeof(mu_Context));
    if (!ctx) {
        SDL_DestroyTexture(atlas_texture);
        SDL_DestroyRenderer(renderer);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return false;
    }
    
    mu_init(ctx);
    ctx->text_width = text_width;
    ctx->text_height = text_height;
    
    return true;
}

bool gui_update(void)
{
    /* Process SDL events */
    SDL_Event e;
    while (SDL_PollEvent(&e)) {
        switch (e.type) {
            case SDL_QUIT:
                return false;
                
            case SDL_MOUSEMOTION:
                mu_input_mousemove(ctx, e.motion.x, e.motion.y);
                break;
                
            case SDL_MOUSEWHEEL:
                mu_input_scroll(ctx, 0, e.wheel.y * -30);
                break;
                
            case SDL_MOUSEBUTTONDOWN:
                mu_input_mousedown(ctx, e.button.x, e.button.y, 
                                   map_sdl_button(e.button.button));
                break;
                
            case SDL_MOUSEBUTTONUP:
                mu_input_mouseup(ctx, e.button.x, e.button.y,
                                 map_sdl_button(e.button.button));
                break;
                
            case SDL_KEYDOWN:
                mu_input_keydown(ctx, map_sdl_key(e.key.keysym.sym));
                break;
                
            case SDL_KEYUP:
                mu_input_keyup(ctx, map_sdl_key(e.key.keysym.sym));
                break;
                
            case SDL_TEXTINPUT:
                mu_input_text(ctx, e.text.text);
                break;
        }
    }
    
    /* Build GUI */
    mu_begin(ctx);
    
    if (mu_begin_window(ctx, "Controls", mu_rect(10, 10, 380, 280))) {
        mu_layout_row(ctx, 2, (int[]){ 100, -1 }, 0);
        
        /* LED display */
        mu_label(ctx, "LED Status:");
        led_color_t led = gui_get_led_color();
        const char* led_names[] = { "OFF", "RED", "GREEN", "WHITE" };
        
        /* Draw colored rectangle for LED */
        mu_Rect r = mu_layout_next(ctx);
        mu_draw_rect(ctx, r, mu_color(
            led_colors[led].r,
            led_colors[led].g,
            led_colors[led].b,
            led_colors[led].a
        ));
        mu_draw_control_text(ctx, led_names[led], r, MU_COLOR_TEXT, MU_OPT_ALIGNCENTER);
        
        mu_layout_row(ctx, 1, (int[]){ -1 }, 0);
        
        /* Button */
        if (mu_button(ctx, "PAIR / UNLOCK BUTTON")) {
            gui_button_callback();
        }
        
        mu_layout_row(ctx, 2, (int[]){ 80, -1 }, 0);
        
        /* Host UART status */
        mu_label(ctx, "Host UART:");
        const char* host_path = uart_get_host_path();
        mu_label(ctx, host_path[0] ? host_path : "(not connected)");
        
        /* Board UART status */
        mu_label(ctx, "Board UART:");
        const char* board_path = uart_get_board_path();
        mu_label(ctx, board_path[0] ? board_path : "(not connected)");
        
        mu_layout_row(ctx, 1, (int[]){ -1 }, 0);
        
        /* Board reconnect input */
        static char board_input[256] = "";
        mu_label(ctx, "Reconnect Board UART:");
        mu_layout_row(ctx, 2, (int[]){ -60, -1 }, 0);
        mu_textbox(ctx, board_input, sizeof(board_input));
        if (mu_button(ctx, "Connect")) {
            if (board_input[0] != '\0') {
                if (uart_reconnect_board(board_input)) {
                    board_input[0] = '\0';  /* Clear on success */
                }
            }
        }
        
        mu_end_window(ctx);
    }
    
    mu_end(ctx);
    
    /* Render */
    SDL_SetRenderDrawColor(renderer, 40, 40, 40, 255);
    SDL_RenderClear(renderer);
    
    render_microui();
    
    SDL_RenderPresent(renderer);
    
    /* Small delay to avoid burning CPU */
    SDL_Delay(16);  /* ~60 FPS */
    
    return true;
}

void gui_shutdown(void)
{
    if (ctx) {
        free(ctx);
        ctx = NULL;
    }
    
    if (atlas_texture) {
        SDL_DestroyTexture(atlas_texture);
        atlas_texture = NULL;
    }
    
    if (renderer) {
        SDL_DestroyRenderer(renderer);
        renderer = NULL;
    }
    
    if (window) {
        SDL_DestroyWindow(window);
        window = NULL;
    }
    
    SDL_Quit();
}
