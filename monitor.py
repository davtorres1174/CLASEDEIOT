# -*- coding: utf-8 -*-
"""
Registra al mismo tiempo:
  1) la telemetría que el Raspberry Pi simulado envía a Azure IoT Hub (temperatura y humedad), y
  2) los indicadores del sistema operativo (CPU, memoria y red del equipo y del navegador).

Uso:
  python monitor.py                 # 15 minutos (por defecto)
  python monitor.py --minutos 10
  python monitor.py --solo-sistema  # sin Azure, solo indicadores del PC (para probar)

La cadena de conexión del endpoint compatible con Event Hubs se lee de la variable de entorno
IOTHUB_EVENTHUB_CS o del archivo .env de esta carpeta (ver .env.ejemplo).
Los datos quedan en la carpeta datos/: telemetria.csv y sistema.csv.
"""
import argparse, csv, json, os, sys, threading, time
from datetime import datetime

import psutil

AQUI = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(AQUI, 'datos')
NAVEGADORES = {'opera.exe'}  # navegador donde corre el simulador (Opera GX); se cambia con --navegador
INTERVALO_S = 2.0

parar = threading.Event()


def leer_cadena_conexion():
    cs = os.environ.get('IOTHUB_EVENTHUB_CS')
    ruta = os.path.join(AQUI, '.env')
    if not cs and os.path.exists(ruta):
        with open(ruta, encoding='utf-8-sig') as f:
            for linea in f:
                linea = linea.strip()
                if linea.startswith('IOTHUB_EVENTHUB_CS='):
                    cs = linea.split('=', 1)[1].strip().strip('"').strip("'")
    return cs


# ------------------------------------------------------------------ telemetría (Azure IoT Hub)
def hilo_telemetria(cs, contador):
    from azure.eventhub import EventHubConsumerClient

    ruta = os.path.join(DATOS, 'telemetria.csv')
    nuevo = not os.path.exists(ruta)
    f = open(ruta, 'a', newline='', encoding='utf-8')
    w = csv.writer(f)
    if nuevo:
        w.writerow(['hora_recepcion', 'hora_encolado', 'dispositivo', 'message_id', 'temperatura_c', 'humedad_pct', 'alerta_temperatura'])

    def on_event(contexto, evento):
        if evento is None:
            return
        try:
            cuerpo = json.loads(evento.body_as_str())
        except Exception:
            return
        props = evento.properties or {}
        alerta = props.get(b'temperatureAlert', props.get('temperatureAlert', b''))
        if isinstance(alerta, bytes):
            alerta = alerta.decode()
        sp = evento.system_properties or {}
        disp = sp.get(b'iothub-connection-device-id', b'')
        disp = disp.decode() if isinstance(disp, bytes) else str(disp)
        encolado = evento.enqueued_time.astimezone().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] if evento.enqueued_time else ''
        w.writerow([datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3], encolado, disp or cuerpo.get('deviceId', ''),
                    cuerpo.get('messageId', ''), cuerpo.get('temperature', ''), cuerpo.get('humidity', ''), alerta])
        f.flush()
        contador[0] += 1
        contador[1] = (cuerpo.get('temperature'), cuerpo.get('humidity'))

    cliente = EventHubConsumerClient.from_connection_string(cs, consumer_group='$Default')
    t = threading.Thread(target=lambda: cliente.receive(on_event=on_event, starting_position='@latest', max_wait_time=5), daemon=True)
    t.start()
    parar.wait()
    cliente.close()
    f.close()


# ------------------------------------------------------------------ indicadores del sistema operativo
def procesos_navegador(cache):
    vivos = {}
    for p in psutil.process_iter(['name']):
        if (p.info['name'] or '').lower() in NAVEGADORES:
            vivos[p.pid] = cache.get(p.pid, p)
            if p.pid not in cache:
                try:
                    p.cpu_percent(None)  # primera llamada: inicializa la medición
                except psutil.Error:
                    pass
    return vivos


def hilo_sistema(estado):
    ruta = os.path.join(DATOS, 'sistema.csv')
    nuevo = not os.path.exists(ruta)
    f = open(ruta, 'a', newline='', encoding='utf-8')
    w = csv.writer(f)
    if nuevo:
        w.writerow(['hora', 'cpu_total_pct', 'memoria_total_pct', 'memoria_usada_mb',
                    'cpu_navegador_pct', 'memoria_navegador_mb', 'procesos_navegador',
                    'red_enviada_kbs', 'red_recibida_kbs'])
    ncpu = psutil.cpu_count() or 1
    cache = procesos_navegador({})
    psutil.cpu_percent(None)
    red0, t0 = psutil.net_io_counters(), time.time()
    while not parar.wait(INTERVALO_S):
        cache = procesos_navegador(cache)
        cpu_nav, mem_nav = 0.0, 0.0
        for p in list(cache.values()):
            try:
                cpu_nav += p.cpu_percent(None) / ncpu  # mismo criterio que el Administrador de tareas (% del total)
                # USS = conjunto de trabajo privado, la misma métrica de la columna "Memoria" del Administrador de tareas
                mem_nav += p.memory_full_info().uss / 1048576
            except psutil.Error:
                cache.pop(p.pid, None)
        red1, t1 = psutil.net_io_counters(), time.time()
        dt = t1 - t0
        enviada = (red1.bytes_sent - red0.bytes_sent) / 1024 / dt
        recibida = (red1.bytes_recv - red0.bytes_recv) / 1024 / dt
        red0, t0 = red1, t1
        vm = psutil.virtual_memory()
        fila = [datetime.now().strftime('%Y-%m-%d %H:%M:%S'), psutil.cpu_percent(None), vm.percent, round(vm.used / 1048576),
                round(cpu_nav, 2), round(mem_nav, 1), len(cache), round(enviada, 2), round(recibida, 2)]
        w.writerow(fila)
        f.flush()
        estado[0] = fila


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--minutos', type=float, default=15)
    ap.add_argument('--solo-sistema', action='store_true')
    ap.add_argument('--navegador', default='opera.exe', help='proceso del navegador del simulador, p. ej. chrome.exe')
    a = ap.parse_args()
    NAVEGADORES.clear()
    NAVEGADORES.add(a.navegador.lower())
    os.makedirs(DATOS, exist_ok=True)
    # cada corrida empieza con archivos limpios; los de corridas anteriores se archivan con la hora
    sello = datetime.now().strftime('%H%M%S')
    for nombre in ('telemetria.csv', 'sistema.csv'):
        ruta = os.path.join(DATOS, nombre)
        if os.path.exists(ruta):
            os.replace(ruta, os.path.join(DATOS, nombre.replace('.csv', f'_anterior_{sello}.csv')))

    hilos, contador, estado = [], [0, None], [None]
    if not a.solo_sistema:
        cs = leer_cadena_conexion()
        if not cs:
            sys.exit('Falta la cadena de conexión. Crea el archivo .env (ver .env.ejemplo) o usa --solo-sistema.')
        if cs.startswith('HostName='):
            sys.exit('El .env tiene la cadena de conexión del DISPOSITIVO (HostName=...). Esa va en el simulador.\n'
                     'Aquí se necesita la del endpoint compatible con Event Hubs (empieza por Endpoint=sb://...):\n'
                     'IoT Hub > Configuración del centro > Puntos de conexión integrados.')
        if not cs.startswith('Endpoint=sb://'):
            sys.exit('La cadena del .env no empieza por Endpoint=sb://. Revisa que copiaste el endpoint compatible con Event Hubs.')
        hilos.append(threading.Thread(target=hilo_telemetria, args=(cs, contador)))
    hilos.append(threading.Thread(target=hilo_sistema, args=(estado,)))
    for h in hilos:
        h.start()

    fin = time.time() + a.minutos * 60
    print(f'Registrando durante {a.minutos:g} min en {DATOS}  (Ctrl+C para detener antes)')
    try:
        while time.time() < fin:
            time.sleep(INTERVALO_S)
            s = estado[0]
            if s:
                ult = contador[1]
                tel = f'mensajes={contador[0]}' + (f' ult T={ult[0]} °C H={ult[1]} %' if ult else '') if not a.solo_sistema else ''
                print(f'\r{s[0][11:]}  CPU={s[1]:5.1f}%  navegador CPU={s[4]:5.1f}% mem={s[5]:7.1f} MB  red↑={s[7]:6.1f} KB/s  {tel}   ',
                      end='', flush=True)
    except KeyboardInterrupt:
        pass
    parar.set()
    for h in hilos:
        h.join(timeout=10)
    print(f'\nListo. Mensajes de telemetría recibidos: {contador[0]}')


if __name__ == '__main__':
    main()
