#include "bsp_system.h"
#include "main.h"

system_parameter sp;

void bsp_system_init(void)
{
    sp.system_ready = 1U;
    sp.system_tick_ms = HAL_GetTick();
    sp.scheduler_cycle_count = 0U;
	sp.system_mode = 0;
    sp.humidity_percent = 79U;
	sp.data_x = 0;
	sp.data_y = 15;
	sp.beep_freq = 2000;
	
}
