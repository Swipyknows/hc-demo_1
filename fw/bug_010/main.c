#include "board.h"

static void uart_putc(char c) { USART_DR(USART1_BASE) = c; }
static void uart_puts(const char *s) { while (*s) uart_putc(*s++); }

#define TICK_HZ           1000          /* SysTick fires every 1 ms */
#define SENSOR_WARMUP_MS  20            /* sensor needs 20 ms after power-up */
#define SENSOR_TIMEOUT_MS 50            /* give up after 50 ms */
#define TIMEOUT_TICKS     (SENSOR_TIMEOUT_MS / 10)

static volatile uint32_t ticks;
static volatile uint32_t sensor_ready;

void SysTick_Handler(void)
{
  ticks++;
  if (ticks >= SENSOR_WARMUP_MS) sensor_ready = 1;
}

static void systick_init(void)
{
  SYST_RVR = 1000 - 1;
  SYST_CVR = 0;
  SYST_CSR = SYST_CSR_ENABLE | SYST_CSR_TICKINT | SYST_CSR_CLKSOURCE;
}

static int wait_sensor(void)
{
  uint32_t start = ticks;
  while (!sensor_ready)
    if (ticks - start > TIMEOUT_TICKS) return 0;
  return 1;
}

int main(void)
{
  USART_CR1(USART1_BASE) = USART_CR1_UE | USART_CR1_TE;
  uart_puts("boot ok\n");
  systick_init();
  uart_puts(wait_sensor() ? "sensor ready\n" : "sensor timeout\n");
  uart_puts("init done\n");
  for (;;);
}
