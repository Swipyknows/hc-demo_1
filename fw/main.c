#include <stdint.h>
#define USART1_SR  (*(volatile uint32_t*)0x40011000)
#define USART1_DR  (*(volatile uint32_t*)0x40011004)
#define USART1_CR1 (*(volatile uint32_t*)0x4001100C)
#define SCB_CFSR   (*(volatile uint32_t*)0xE000ED28)

static void uart_putc(char c){ USART1_DR = c; }
static void uart_puts(const char*s){ while(*s) uart_putc(*s++); }

extern uint32_t _estack, _etext, _sdata, _edata, _sbss, _ebss;
int main(void);

void Reset_Handler(void){
  uint32_t *src=&_etext,*dst=&_sdata;
  while(dst<&_edata) *dst++=*src++;
  for(dst=&_sbss; dst<&_ebss;) *dst++=0;
  main();
  for(;;);
}
void HardFault_Handler(void){ uart_puts("HARDFAULT\n"); for(;;); }
void Default_Handler(void){ for(;;); }

__attribute__((section(".isr_vector"), used))
void (*const vectors[16])(void) = {
  (void(*)(void))&_estack, Reset_Handler, Default_Handler, HardFault_Handler,
  Default_Handler, Default_Handler, Default_Handler
};

/* SEEDED BUG: callback never registered (NULL function pointer) */
void (*rx_callback)(void);
static void on_rx(void){ uart_puts("rx ok\n"); }

int main(void){
  USART1_CR1 = (1<<13)|(1<<3);   /* UE | TE */
  uart_puts("boot ok\n");
  rx_callback();                 /* call through NULL function pointer */
  uart_puts("init done\n");
  for(;;);
}
