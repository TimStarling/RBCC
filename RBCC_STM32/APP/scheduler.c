#include "scheduler.h"
#include "app_tasks.h"
#include "bsp_system.h"
#include "main.h"
#include "dht_app.h"
#include "ws2812_app.h"

typedef void (*task_function_t)(void);

typedef struct
{
    task_function_t task_func;
    uint32_t period_ms;
    uint32_t last_run_ms;
} scheduled_task_t;

static scheduled_task_t schedule_tasks[] =
{
    {app_key_task,       10U,   0U},
    {app_control_task,   20U,   0U},
    {app_light_sensor_task, 250U, 0U},
	{app_uart_task,     250U,   0U},
    {dht_app_task,      250U,   0U},
    {app_temperature_sensor_task, 500U, 0U},
    {app_heartbeat_task, 500U,  0U},
	{app_beep_task, 20U, 0U}
};

static uint8_t task_count;

void schedule_init(void)
{
    uint8_t i;
    uint32_t now_ms;
	
    bsp_system_init();
    app_tasks_init();
    dht_app_init();
    ws2812_app_init();
    ws2812_app_show_coordinate((uint8_t)sp.data_x, 0U);

    now_ms = HAL_GetTick();
    task_count = (uint8_t)(sizeof(schedule_tasks) / sizeof(schedule_tasks[0]));

    for (i = 0U; i < task_count; i++)
    {
        schedule_tasks[i].last_run_ms = now_ms;
    }
}

void schedule_run(void)
{
    uint8_t i;
    uint32_t now_ms;

    now_ms = HAL_GetTick();
    sp.system_tick_ms = now_ms;
    sp.scheduler_cycle_count++;

    for (i = 0U; i < task_count; i++)
    {
        if ((uint32_t)(now_ms - schedule_tasks[i].last_run_ms) >=
            schedule_tasks[i].period_ms)
        {
            schedule_tasks[i].last_run_ms = now_ms;
            schedule_tasks[i].task_func();
        }
    }

}
