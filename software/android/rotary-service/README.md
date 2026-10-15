# rotary-service (plan)

The dial is a Piher PSC-360 (contactless, 5 V ratiometric analog output, endless) read on Verdin ADC_1, plus a separate push switch on GPIO_1 (see `../../../display` J11). The service unwraps the angle into detents, debounces the click, and injects rotary / key events for the cluster UI and for CarPlay / Android Auto. The dial's 5 V is switched off in sleep by `CTRL_SLEEP_MOCI#`, so the service must treat the first reading after wake as a re-zero.
