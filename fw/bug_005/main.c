#include "board.h"

static void uart_putc(char c) { USART_DR(USART1_BASE) = c; }
static void uart_puts(const char *s) { while (*s) uart_putc(*s++); }

static volatile uint32_t ticks;

/* 1 ms system tick */
void Systick_Handler(void)
{
  ticks++;
}

static void systick_init(void)
{
  SYST_RVR = 1000 - 1;
  SYST_CVR = 0;
  SYST_CSR = SYST_CSR_ENABLE | SYST_CSR_TICKINT | SYST_CSR_CLKSOURCE;
}

int main(void)
{
  USART_CR1(USART1_BASE) = USART_CR1_UE | USART_CR1_TE;
  uart_puts("boot ok\n");
  systick_init();
  while (ticks < 10);
  uart_puts("tick ok\n");
  uart_puts("init done\n");
  for (;;);
}
