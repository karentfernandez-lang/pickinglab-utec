"""Reglas del modelo de picking: funciones sin dependencia de Streamlit."""
import math
from functools import lru_cache

DEFAULT_SKUS = [
    {'SKU':'A','p':100,'d':10,'P':0.8,'b':1,'c':1,'u':3},
    {'SKU':'B','p':140,'d':30,'P':1,'b':1,'c':2,'u':4},
    {'SKU':'C','p':60,'d':5,'P':0.6,'b':1,'c':1,'u':2},
    {'SKU':'D','p':40,'d':20,'P':1,'b':1,'c':1,'u':3},
    {'SKU':'E','p':80,'d':20,'P':0.9,'b':1,'c':1,'u':2},
    {'SKU':'F','p':30,'d':6,'P':0.5,'b':1,'c':1,'u':2},
]
DEFAULT_LAYOUT = [
 ['L01','PASILLO','PASILLO','PASILLO','L05'],
 ['L02','PASILLO','PASILLO','PASILLO','L06'],
 ['L03','PASILLO','PASILLO','PASILLO','L07'],
 ['L04','PASILLO','PASILLO','PASILLO','L08'],
 ['PASILLO']*5,
]

def entero(v, campo, minimo=0):
    if isinstance(v,bool): raise ValueError(f'{campo}: debe ser un número entero.')
    try: n=float(v)
    except (TypeError,ValueError): raise ValueError(f'{campo}: debe ser un número entero.')
    if not math.isfinite(n) or not n.is_integer() or n < minimo:
        raise ValueError(f'{campo}: debe ser un entero mayor o igual a {minimo}.')
    return int(n)

def numero(v,campo,positivo=False):
    try: n=float(v)
    except (TypeError,ValueError): raise ValueError(f'{campo}: debe ser numérico.')
    if not math.isfinite(n) or (n<=0 if positivo else n<0):
        raise ValueError(f'{campo}: debe ser {"mayor que cero" if positivo else "no negativo"}.')
    return n

def preparar_skus(rows, reserva, picking, reposicion):
    reserva=numero(reserva,'Tiempo en reserva',True)
    picking=numero(picking,'Tiempo en picking',True)
    reposicion=numero(reposicion,'Tiempo de reposición',False)
    if picking >= reserva: raise ValueError('El tiempo de picking debe ser menor que el de reserva para este modelo de ahorro.')
    if not rows: raise ValueError('Agregá al menos un SKU.')
    resultado=[]; vistos=set(); s=reserva-picking
    for i,row in enumerate(rows,1):
        sku=str(row.get('SKU','')).strip()
        if not sku: raise ValueError(f'Fila {i}: falta el código SKU.')
        if sku.upper() in vistos: raise ValueError(f'Código SKU duplicado: {sku}.')
        vistos.add(sku.upper())
        p=entero(row.get('p'),f'{sku}: p')
        d=numero(row.get('d'),f'{sku}: d')
        P=numero(row.get('P'),f'{sku}: P')
        b=numero(row.get('b'),f'{sku}: b',True)
        c=entero(row.get('c'),f'{sku}: c',1)
        u=entero(row.get('u'),f'{sku}: u',1)
        l=max(math.ceil(P/b),c)
        if l>u: raise ValueError(f'{sku}: l={l} supera u={u}. Corregí P, b, c o u.')
        opciones=[('Nada',0,0.0),('Mínimo',l,s*p-reposicion*d),('Todo',u,s*p)]
        # Si mínimo y todo ocupan el mismo espacio, no se permite contabilizar ahorros diferentes.
        # El modelo define que u cubre todo y por tanto no necesita reposición.
        if l==u: opciones=[('Nada',0,0.0),('Todo',u,s*p)]
        resultado.append({'SKU':sku,'p':p,'d':d,'P':P,'b':b,'c':c,'u':u,'l':l,'s':s,
                          'B_min':s*p-reposicion*d,'B_todo':s*p,'opciones':opciones})
    return resultado

def validar_layout(grid,N):
    N=entero(N,'N')
    if not grid or not grid[0]: raise ValueError('El layout no puede estar vacío.')
    ancho=len(grid[0]); dirs=[]; vistos=set()
    for i,row in enumerate(grid,1):
        if len(row)!=ancho: raise ValueError('El layout debe ser rectangular.')
        for j,cell in enumerate(row,1):
            v=str(cell).strip().upper()
            if not v: raise ValueError(f'Layout fila {i}, columna {j}: casilla vacía.')
            if v in ('PASILLO','BLOQUEADO'): continue
            if v in vistos: raise ValueError(f'Dirección repetida en el layout: {v}.')
            vistos.add(v); dirs.append((v,i,j))
    if N>len(dirs): raise ValueError(f'N={N} supera las {len(dirs)} direcciones del layout.')
    # Prioridad: desde la fila inferior, de izquierda a derecha, excluyendo PASILLO/BLOQUEADO.
    return [x[0] for x in sorted(dirs,key=lambda x:(-x[1],x[2],x[0]))][:N]

def optimizar(items,N,limite=3):
    """Programación dinámica exacta: para cada capacidad conserva las mejores propuestas distintas."""
    N=entero(N,'N')
    estados={0:[(0.0,tuple())]}
    for item in items:
        nuevos={}
        for ocupado,sols in estados.items():
            for ahorro,elecciones in sols:
                for nombre,espacio,beneficio in item['opciones']:
                    n=ocupado+espacio
                    if n>N: continue
                    nuevos.setdefault(n,[]).append((ahorro+beneficio,elecciones+((nombre,espacio,beneficio),)))
        # Conservar los mejores por capacidad exacta. Para la solución óptima basta 1,
        # para comparar propuestas se conservan las mejores 3 por capacidad.
        estados={k:sorted(v,key=lambda t:(-round(t[0],10),tuple(x[0] for x in t[1])))[:limite] for k,v in nuevos.items()}
    soluciones=[]
    for ocupado,vals in estados.items():
        for ahorro,elecciones in vals:
            soluciones.append({'ubicaciones':ocupado,'ahorro':round(ahorro,8),'decisiones':[
                {'SKU':it['SKU'],'opcion':e[0],'ubicaciones':e[1],'ahorro':round(e[2],8)}
                for it,e in zip(items,elecciones)]})
    soluciones.sort(key=lambda x:(-x['ahorro'],x['ubicaciones'],tuple(y['opcion'] for y in x['decisiones'])))
    return soluciones[:limite]

def asignar_direcciones(solucion,items,direcciones):
    asignadas={}; por_sku={it['SKU']:[] for it in items}
    prioridad=sorted(solucion['decisiones'],key=lambda x:(-next(it['p'] for it in items if it['SKU']==x['SKU']),x['SKU']))
    libres=list(direcciones)
    for decision in prioridad:
        for _ in range(decision['ubicaciones']):
            if not libres: raise ValueError('No quedan direcciones disponibles.')
            direccion=libres.pop(0)
            asignadas[direccion]=decision['SKU']
            por_sku[decision['SKU']].append(direccion)
    return asignadas,por_sku
