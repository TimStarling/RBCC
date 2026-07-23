#ifndef APP_TASKS_H
#define APP_TASKS_H

#include <stdint.h>

#define APP_KEY0_MASK              0x01U
#define APP_KEY1_MASK              0x02U
#define APP_KEY2_MASK              0x04U
#define APP_KEY3_MASK              0x08U
#define APP_KEY_ALL_MASK           0x0FU

typedef struct
{
    volatile uint8_t current;
    volatile uint8_t down;
    volatile uint8_t up;
    volatile uint8_t long_press;
} app_key_status_t;

extern app_key_status_t g_app_key_status;

void beep_play(int freq);
void beep_control(int mode);
void app_tasks_init(void);
void app_key_task(void);
uint8_t app_key_get_current(void);
uint8_t app_key_get_down(void);
uint8_t app_key_get_up(void);
uint8_t app_key_get_long_press(void);
uint8_t app_key_take_down(uint8_t key_mask);
uint8_t app_key_take_up(uint8_t key_mask);
uint8_t app_key_take_long_press(uint8_t key_mask);
void app_control_task(void);
void app_light_sensor_task(void);
void app_temperature_sensor_task(void);
void app_uart_task(void);
void app_heartbeat_task(void);
void app_beep_task(void);


#endif
