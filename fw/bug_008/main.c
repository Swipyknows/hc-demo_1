#include "board.h"

static void uart_putc(char c) { USART_DR(USART1_BASE) = c; }
static void uart_puts(const char *s) { while (*s) uart_putc(*s++); }
static void uart_putu(uint32_t v)
{
  char b[11]; int i = 10; b[i] = 0;
  do { b[--i] = '0' + v % 10; v /= 10; } while (v);
  uart_puts(&b[i]);
}

/* Sensor bank */
static uint32_t samples[4];
static uint32_t sample_count;

static void sensors_init(void)
{
  samples[0] = 20; samples[1] = 24; samples[2] = 26; samples[3] = 30;
  sample_count = 4;
}

static void report_average(void)
{
  uint32_t total = 0;
  for (uint32_t i = 0; i < 4; i++) total += samples[i];
  uart_puts("avg ");
  uart_putu(total / sample_count);
  uart_puts("\n");
}

int main(void)
{
  SCB_CCR |= SCB_CCR_DIV_0_TRP;          /* safety: trap on divide-by-zero */
  USART_CR1(USART1_BASE) = USART_CR1_UE | USART_CR1_TE;
  uart_puts("boot ok\n");
  report_average();
  sensors_init();
  uart_puts("init done\n");
  for (;;);
}
