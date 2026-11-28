#include "board.h"

static void uart_putc(char c) { USART_DR(USART1_BASE) = c; }
static void uart_puts(const char *s) { while (*s) uart_putc(*s++); }

/* TIM2 provides the periodic heartbeat for the control loop */
static void heartbeat_timer_init(void)
{
  TIM2_CR1 = 0;
  TIM2_PSC = 0;
  TIM2_ARR = 1000;
  TIM2_CNT = 0;
  TIM2_SR = 0;
  TIM2_DIER = TIM_DIER_UIE;          /* update event flag/interrupt (IRQ stays masked in NVIC) */
  TIM2_CR1 = (1u << 1);
}

static int wait_heartbeat(void)
{
  uint32_t spins = 2000000;
  while (!(TIM2_SR & TIM_SR_UIF))
    if (--spins == 0) return 0;
  TIM2_SR = 0;
  return 1;
}

int main(void)
{
  USART_CR1(USART1_BASE) = USART_CR1_UE | USART_CR1_TE;
  uart_puts("boot ok\n");
  heartbeat_timer_init();
  uart_puts(wait_heartbeat() ? "tick ok\n" : "tick timeout\n");
  uart_puts("init done\n");
  for (;;);
}
