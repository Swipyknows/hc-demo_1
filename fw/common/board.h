/* board.h - register map for the QEMU 'netduino2' machine (STM32F205, Cortex-M3).
 * Shared by every benchmark case. Read-only for the debugging agent. */
#ifndef BOARD_H
#define BOARD_H
#include <stdint.h>

#define REG32(addr)   (*(volatile uint32_t *)(addr))

/* USART1 (connected to the QEMU serial console) and USART2 (not connected) */
#define USART1_BASE   0x40011000u
#define USART2_BASE   0x40004400u
#define USART_SR(b)   REG32((b) + 0x00)
#define USART_DR(b)   REG32((b) + 0x04)
#define USART_BRR(b)  REG32((b) + 0x08)
#define USART_CR1(b)  REG32((b) + 0x0C)
#define USART_CR1_UE  (1u << 13)
#define USART_CR1_TE  (1u << 3)
#define USART_CR1_RE  (1u << 2)

/* General-purpose timer TIM2 */
#define TIM2_BASE     0x40000000u
#define TIM2_CR1      REG32(TIM2_BASE + 0x00)
#define TIM2_DIER     REG32(TIM2_BASE + 0x0C)
#define TIM2_SR       REG32(TIM2_BASE + 0x10)
#define TIM2_CNT      REG32(TIM2_BASE + 0x24)
#define TIM2_PSC      REG32(TIM2_BASE + 0x28)
#define TIM2_ARR      REG32(TIM2_BASE + 0x2C)
#define TIM_CR1_CEN   (1u << 0)
#define TIM_SR_UIF    (1u << 0)
#define TIM_DIER_UIE  (1u << 0)

/* SysTick */
#define SYST_CSR      REG32(0xE000E010)
#define SYST_RVR      REG32(0xE000E014)
#define SYST_CVR      REG32(0xE000E018)
#define SYST_CSR_ENABLE    (1u << 0)
#define SYST_CSR_TICKINT   (1u << 1)
#define SYST_CSR_CLKSOURCE (1u << 2)

/* System Control Block */
#define SCB_CCR       REG32(0xE000ED14)
#define SCB_CCR_DIV_0_TRP  (1u << 4)
#define SCB_CFSR      REG32(0xE000ED28)
#define SCB_HFSR      REG32(0xE000ED2C)

/* Memory map */
#define SRAM_BASE     0x20000000u
#define SRAM_SIZE     (128u * 1024u)

#endif
