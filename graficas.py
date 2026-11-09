# -*- coding: utf-8 -*-
"""
Genera las gráficas y los resúmenes del artículo a partir de datos/telemetria.csv y datos/sistema.csv.

Uso:  python graficas.py
Salida en la carpeta graficas/:
  figura7_telemetria.png  -> temperatura y humedad en el tiempo
  figura8_recursos.png    -> CPU, memoria y red del equipo durante la simulación
  resumen.txt             -> valores para las Tablas 3 y 4
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, 'datos')
SALIDA = os.path.join(AQUI, 'graficas')
os.makedirs(SALIDA, exist_ok=True)

plt.rcParams.update({'font.family': 'Times New Roman', 'font.size': 11, 'axes.grid': True, 'grid.alpha': 0.3,
                     'axes.spines.top': False, 'axes.spines.right': False})
AZUL, NARANJA, VERDE, GRIS = '#1F5AA6', '#D9711C', '#2E8B57', '#7F7F7F'
fmt_hora = mdates.DateFormatter('%H:%M')
lineas = []


def guardar(fig, nombre):
    ruta = os.path.join(SALIDA, nombre)
    fig.savefig(ruta, dpi=200, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print('Gráfica:', ruta)


# ------------------------------------------------------------------ telemetría
ruta_tel = os.path.join(DATOS, 'telemetria.csv')
if os.path.exists(ruta_tel):
    tel = pd.read_csv(ruta_tel)
    tel['t'] = pd.to_datetime(tel['hora_encolado'].where(tel['hora_encolado'].notna(), tel['hora_recepcion']))
    tel = tel.sort_values('t').reset_index(drop=True)
    # huecos (> 5 s sin mensajes): se corta la línea y se sombrea el tramo
    hueco = tel['t'].diff().dt.total_seconds() > 5
    tramos = [(tel['t'][k - 1], tel['t'][k]) for k in tel.index[hueco]]
    grupo = hueco.cumsum()
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
    for ax, col, color in [(a1, 'temperatura_c', NARANJA), (a2, 'humedad_pct', AZUL)]:
        for _, g in tel.groupby(grupo):
            ax.plot(g['t'], g[col], color=color, lw=1.0, marker='o', ms=2)
        for x0, x1 in tramos:
            ax.axvspan(x0, x1, color=GRIS, alpha=0.15, lw=0)
    a1.axhline(30, color=GRIS, ls='--', lw=1)
    a1.text(1.0, 30.25, 'umbral de alerta (30 °C)', color=GRIS, fontsize=9, va='bottom', ha='right',
            transform=a1.get_yaxis_transform())
    a1.set_ylabel('Temperatura (°C)')
    a1.set_ylim(top=33.5)
    a2.set_ylabel('Humedad relativa (%)')
    # las zonas grises se explican en el pie de figura del artículo
    a2.set_xlabel('Hora')
    a2.xaxis.set_major_formatter(fmt_hora)
    guardar(fig, 'figura7_telemetria.png')

    dur = (tel['t'].max() - tel['t'].min()).total_seconds()
    periodo = tel['t'].diff().dt.total_seconds().median()
    alertas = tel['alerta_temperatura'].astype(str).str.lower().eq('true').sum()
    lineas += ['TABLA 3 - Resumen estadístico de la telemetría recibida',
               f'  Mensajes recibidos: {len(tel)}   Duración: {dur/60:.1f} min   Periodo mediano de envío: {periodo:.2f} s   Mensajes con alerta (>30 °C): {alertas}']
    for col, nom in [('temperatura_c', 'Temperatura (°C)'), ('humedad_pct', 'Humedad (%)')]:
        s = tel[col]
        lineas.append(f'  {nom:18s} mín={s.min():.2f}  máx={s.max():.2f}  promedio={s.mean():.2f}  desv. estándar={s.std():.2f}')
    lineas.append('')
else:
    print('No hay datos/telemetria.csv (se omite la Figura 7).')

# ------------------------------------------------------------------ sistema operativo
ruta_sis = os.path.join(DATOS, 'sistema.csv')
if os.path.exists(ruta_sis):
    sis = pd.read_csv(ruta_sis)
    sis['t'] = pd.to_datetime(sis['hora'])
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(8, 6.5), sharex=True)
    a1.plot(sis['t'], sis['cpu_total_pct'], color=GRIS, lw=1.2, label='CPU total del equipo')
    a1.plot(sis['t'], sis['cpu_navegador_pct'], color=NARANJA, lw=1.4, label='CPU de Opera GX (simulador)')
    a1.set_ylabel('CPU (%)')
    a1.legend(loc='upper right', fontsize=9, frameon=False)
    a2.plot(sis['t'], sis['memoria_navegador_mb'], color=AZUL, lw=1.4)
    a2.set_ylabel('Memoria de\nOpera GX (MB)')
    a3.plot(sis['t'], sis['red_enviada_kbs'], color=VERDE, lw=1.4, label='Enviada')
    a3.plot(sis['t'], sis['red_recibida_kbs'], color=GRIS, lw=1.0, alpha=0.8, label='Recibida')
    a3.set_ylabel('Red (KB/s)')
    a3.set_xlabel('Hora')
    a3.legend(loc='upper right', fontsize=9, frameon=False)
    a3.xaxis.set_major_formatter(fmt_hora)
    guardar(fig, 'figura8_recursos.png')

    lineas.append('TABLA 4 - Valores registrados por el script (promedio | máximo)')
    for col, nom in [('cpu_total_pct', 'CPU total (%)'), ('cpu_navegador_pct', 'CPU del navegador (%)'),
                     ('memoria_navegador_mb', 'Memoria del navegador (MB)'), ('red_enviada_kbs', 'Red enviada (KB/s)')]:
        lineas.append(f'  {nom:28s} {sis[col].mean():9.2f} | {sis[col].max():9.2f}')
    lineas.append(f'  Muestras: {len(sis)}  (cada 2 s)')
else:
    print('No hay datos/sistema.csv (se omite la Figura 8).')

if lineas:
    texto = '\n'.join(lineas)
    open(os.path.join(SALIDA, 'resumen.txt'), 'w', encoding='utf-8').write(texto + '\n')
    print('\n' + texto)
