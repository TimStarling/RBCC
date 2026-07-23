#include "sensor_app.h"
#include "bsp_system.h"
#include "adc.h"

static HAL_StatusTypeDef adc_read_average(ADC_HandleTypeDef *hadc,
                                          uint8_t sample_count,
                                          uint16_t *average)
{
    uint32_t sum = 0U;
    uint8_t i;

    if ((hadc == NULL) || (average == NULL) || (sample_count == 0U))
    {
        return HAL_ERROR;
    }

    for (i = 0U; i < sample_count; i++)
    {
        if (HAL_ADC_Start(hadc) != HAL_OK)
        {
            return HAL_ERROR;
        }

        if (HAL_ADC_PollForConversion(hadc, 10U) != HAL_OK)
        {
            HAL_ADC_Stop(hadc);
            return HAL_TIMEOUT;
        }

        sum += HAL_ADC_GetValue(hadc);
        HAL_ADC_Stop(hadc);
    }

    *average = (uint16_t)(sum / sample_count);
    return HAL_OK;
}

void sensor_app_init(void)
{
}

void light_sensor_task(void)
{
    uint32_t level;
    uint16_t light_average;

    if (adc_read_average(&hadc3, 10U, &light_average) != HAL_OK)
    {
        return;
    }

    sp.light_raw = light_average;

    /*
     * 正点原子例程换算：
     * 0 = 最暗，100 = 最亮
     */
    level = sp.light_raw / 40U;

    if (level > 100U)
    {
        level = 100U;
    }

    sp.light_percent = (uint8_t)(100U - level);
}

void temperature_sensor_task(void)
{
    uint16_t temperature_average;
    float voltage;
    float temperature;

    /* Displayed temperature is calculated from exactly 30 ADC samples. */
    if (adc_read_average(&hadc1, 30U, &temperature_average) != HAL_OK)
    {
        return;
    }

    sp.temperature_raw = temperature_average;

    voltage = (float)sp.temperature_raw * 3.3f / 4095.0f;

    temperature =
        (voltage - 0.76f) / 0.0025f + 25.0f;

    sp.mcu_temperature_centi_c =
        (int16_t)(temperature * 100.0f);
}
