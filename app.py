import io
import json
import html
import math
import csv
import unicodedata
import pandas as pd
import streamlit as st
from motor import DEFAULT_SKUS, DEFAULT_LAYOUT, preparar_skus, validar_layout, optimizar, asignar_direcciones

def normalizar_columna(nombre):
    """Reconoce encabezados comunes sin confundir p con P."""
    raw=str(nombre).strip()
    if raw in ('p','P'): return raw
    normal=unicodedata.normalize('NFKD',raw).encode('ascii','ignore').decode().lower()
    normal=' '.join(normal.replace('_',' ').replace('-',' ').split())
    alias={
        'sku':'SKU','codigo':'SKU','codigo sku':'SKU','producto':'SKU',
        'extracciones':'p','extracciones semana':'p','picks':'p','picks semana':'p',
        'pallets semana':'d','pallets por semana':'d','demanda pallets':'d',
        'inventario':'P','inventario pallets':'P','inventario hasta reposicion':'P',
        'pallets por ubicacion':'b','capacidad por ubicacion':'b',
        'frentes':'c','frentes minimos':'c',
        'ubicaciones':'u','ubicaciones para todo':'u','ubicaciones totales':'u',
    }
    return alias.get(normal,raw)


def leer_productos(archivo):
    """Importa datos estructurados, sin intentar adivinar tablas en PDFs o imágenes."""
    nombre=archivo.name.lower()
    contenido=archivo.getvalue()
    if nombre.endswith(('.xlsx','.xls')):
        df=pd.read_excel(io.BytesIO(contenido))
    elif nombre.endswith('.json'):
        obj=json.loads(contenido.decode('utf-8-sig'))
        if isinstance(obj,dict): obj=obj.get('productos',obj.get('skus',obj.get('datos',obj)))
        if not isinstance(obj,list): raise ValueError('El JSON debe contener una lista de productos o un objeto con la clave productos/skus/datos.')
        df=pd.DataFrame(obj)
    elif nombre.endswith(('.csv','.tsv','.txt')):
        texto=contenido.decode('utf-8-sig')
        sep='\t' if nombre.endswith('.tsv') else None
        try:
            df=pd.read_csv(io.StringIO(texto),sep=sep,engine='python')
        except Exception as e:
            raise ValueError('El texto debe tener una tabla con encabezados y columnas separadas por coma, punto y coma o tabulación.') from e
    else:
        raise ValueError('Formato no compatible. Usá XLSX, XLS, CSV, TSV, TXT tabular o JSON.')
    if df.empty: raise ValueError('El archivo no contiene productos.')
    df.columns=[normalizar_columna(c) for c in df.columns]
    if df.columns.duplicated().any(): raise ValueError('Hay columnas repetidas después de reconocer los encabezados.')
    requeridas=['SKU','p','d','P','b','c','u']
    faltantes=[c for c in requeridas if c not in df.columns]
    if faltantes: raise ValueError('Faltan columnas: '+', '.join(faltantes)+'. Las columnas obligatorias son SKU, p, d, P, b, c, u.')
    df=df[requeridas].copy()
    if df.isna().any().any(): raise ValueError('Hay valores vacíos en los datos de los SKU.')
    return df


st.set_page_config(page_title='PickingLab | Organización de almacenes',page_icon='📦',layout='wide')
st.markdown('''<style>
.block-container{padding-top:1.6rem;max-width:1300px}
h1,h2,h3{letter-spacing:-.03em}
[data-testid="stMetric"]{background:rgba(128,128,128,.07);padding:14px;border-radius:12px;border:1px solid rgba(128,128,128,.16)}
.celda{border:1px solid #8793a55a;border-radius:10px;min-height:78px;padding:12px;text-align:center;margin:3px 0}
.direccion{font-size:.78rem;opacity:.72}.sku{font-size:1.3rem;font-weight:750}
</style>''',unsafe_allow_html=True)

st.title('📦 PickingLab · UTEC')
st.caption('Organización del área adelantada de picking de cajas desde pallets · Modelo didáctico Nada / Mínimo / Todo')

if 'skus' not in st.session_state: st.session_state.skus=pd.DataFrame(DEFAULT_SKUS)
if 'layout' not in st.session_state: st.session_state.layout=pd.DataFrame(DEFAULT_LAYOUT)
if 'N' not in st.session_state: st.session_state.N=8
if 'reserva' not in st.session_state: st.session_state.reserva=2.0
if 'picking' not in st.session_state: st.session_state.picking=1.0
if 'reposicion' not in st.session_state: st.session_state.reposicion=3.0


def restaurar_caso():
    st.session_state.skus=pd.DataFrame(DEFAULT_SKUS)
    st.session_state.layout=pd.DataFrame(DEFAULT_LAYOUT)
    st.session_state.N=8
    st.session_state.reserva=2.0
    st.session_state.picking=1.0
    st.session_state.reposicion=3.0
    for key in ('sku_editor','layout_editor'): st.session_state.pop(key,None)

def cargar_segundo():
    st.session_state.skus=pd.DataFrame([
        {'SKU':'Q1','p':65,'d':9,'P':.9,'b':1,'c':1,'u':3},
        {'SKU':'Q2','p':90,'d':16,'P':1.3,'b':1,'c':2,'u':3},
        {'SKU':'Q3','p':40,'d':5,'P':.7,'b':1,'c':1,'u':2},
        {'SKU':'Q4','p':20,'d':4,'P':.6,'b':1,'c':1,'u':2}])
    st.session_state.layout=pd.DataFrame([
        ['Q01','PASILLO','Q02','Q03'],
        ['Q04','PASILLO','BLOQUEADO','Q05'],
        ['Q06','PASILLO','Q07','Q08'],
        ['PASILLO','PASILLO','PASILLO','PASILLO']])
    st.session_state.N=7
    st.session_state.reserva=2.5
    st.session_state.picking=1.0
    st.session_state.reposicion=2.0
    for key in ('sku_editor','layout_editor'): st.session_state.pop(key,None)

with st.sidebar:
    st.header('Parámetros del almacén')
    N=st.number_input('N · ubicaciones disponibles',min_value=0,step=1,key='N')
    reserva=st.number_input('Extracción desde reserva (min)',min_value=0.01,step=.25,key='reserva')
    picking=st.number_input('Extracción desde picking (min)',min_value=0.01,step=.25,key='picking')
    reposicion=st.number_input('Reposición por pallet (min)',min_value=0.0,step=.25,key='reposicion')
    st.caption('Los tiempos son promedios fijos; la actividad corresponde a una semana.')
    st.button('Restaurar datos de ejemplo',use_container_width=True,on_click=restaurar_caso)

pestanas=st.tabs(['1 · Datos','2 · Cálculos','3 · Optimización','4 · Layout','5 · Pruebas'])
with pestanas[0]:
    st.subheader('Datos de los productos')
    st.info('**Empezá acá:** editá los SKU o importá una planilla. Los tiempos y N están en el panel lateral. Después entrá en «2 · Cálculos» para revisar cada cuenta.')
    st.write('Podés editar, agregar o eliminar filas. **p** = extracciones semanales; **d** = pallets equivalentes movidos por semana; **P** = inventario hasta la reposición; **b** = pallets por ubicación; **c** = frentes mínimos; **u** = ubicaciones para todo.')
    st.markdown('#### Importar productos')
    st.caption('Formatos admitidos: Excel (.xlsx, .xls), CSV, TSV, TXT tabular y JSON. Los archivos deben contener datos estructurados con los campos SKU, p, d, P, b, c y u. No se admiten PDF ni imágenes escaneadas.')
    carga=st.file_uploader('Seleccionar archivo de productos',type=['csv','xlsx','xls','tsv','txt','json'],key='sku_upload')
    if carga is not None:
        try:
            df_importado=leer_productos(carga)
            # Validar antes de reemplazar los productos actuales.
            preparar_skus(df_importado.to_dict('records'),reserva,picking,reposicion)
            st.caption(f'Vista previa: {len(df_importado)} productos reconocidos. Revisá los datos antes de reemplazar la tabla.')
            st.dataframe(df_importado,hide_index=True,use_container_width=True)
            if st.button('Confirmar importación y reemplazar productos',type='primary'):
                st.session_state.skus=df_importado.copy()
                st.session_state.pop('sku_editor',None)
                st.rerun()
        except Exception as e:
            st.error(f'No se pudo importar el archivo: {e}')
    st.markdown('#### Editar o eliminar SKU')
    st.caption('Para eliminar productos completos, seleccioná sus códigos y pulsá el botón. También podés editar o agregar filas en la tabla.')
    if st.session_state.pop('_limpiar_sku_eliminar', False):
        st.session_state['sku_eliminar'] = []
    codigos=[str(v) for v in st.session_state.skus['SKU'].tolist() if pd.notna(v) and str(v).strip()]
    # El selector conserva el estado entre ejecuciones; se limpia en el callback del botón.
    seleccion=st.multiselect('Seleccionar SKU para eliminar',options=list(dict.fromkeys(codigos)),key='sku_eliminar')
    if st.button('🗑️ Eliminar SKU seleccionados',disabled=not seleccion):
        restantes=st.session_state.skus.loc[~st.session_state.skus['SKU'].astype(str).isin(seleccion)].copy()
        if restantes.empty:
            st.error('Debe quedar al menos un SKU. Importá otro archivo si querés reemplazarlos todos.')
        else:
            st.session_state.skus=restantes.reset_index(drop=True)
            st.session_state.pop('sku_editor',None)
            st.session_state['_limpiar_sku_eliminar'] = True
            # No modificar sku_eliminar aquí: el multiselect ya fue instanciado.
            st.rerun()
    skus_edit=st.data_editor(st.session_state.skus,num_rows='dynamic',hide_index=True,use_container_width=True,key='sku_editor',column_config={
        'SKU':st.column_config.TextColumn('SKU',required=True),
        'p':st.column_config.NumberColumn('p · extracciones/semana'),
        'd':st.column_config.NumberColumn('d · pallets/semana',format='%.2f'),
        'P':st.column_config.NumberColumn('P · pallets',format='%.2f'),
        'b':st.column_config.NumberColumn('b · pallets/ubicación',format='%.2f'),
        'c':st.column_config.NumberColumn('c · frentes'),
        'u':st.column_config.NumberColumn('u · ubicaciones')})
    st.session_state.skus=skus_edit.copy()
    st.caption('Atención: P mayúscula y p minúscula son datos diferentes. Usá punto decimal al escribir, por ejemplo 0.8.')

with pestanas[3]:
    st.subheader('Diseñá el plano del almacén')
    st.info('**Cómo usar esta sección:** 1) Elegí las filas y columnas. 2) Escribí un código único por ubicación (L01, L02…), PASILLO o BLOQUEADO. 3) Mirá abajo cómo se asignan los productos automáticamente. Los pasillos y bloqueos nunca cuentan como ubicaciones.')
    st.caption('También podés subir un Excel o CSV con el plano, sin encabezados. Cada celda es una posición física.')
    layout_file=st.file_uploader('Importar layout (Excel o CSV)',type=['xlsx','csv'],key='layout_upload')
    if layout_file is not None and st.button('Cargar layout del archivo'):
        try:
            nuevo=pd.read_excel(layout_file,header=None,dtype=str) if layout_file.name.lower().endswith('xlsx') else pd.read_csv(layout_file,header=None,dtype=str,sep=None,engine='python')
            if nuevo.isna().any().any(): raise ValueError('Hay casillas vacías. Completalas con PASILLO o BLOQUEADO.')
            st.session_state.layout=nuevo.astype(str)
            st.session_state.pop('layout_editor',None)
            st.rerun()
        except Exception as e: st.error(f'No se pudo cargar el layout: {e}')
    st.download_button('Descargar layout de ejemplo (CSV)',pd.DataFrame(DEFAULT_LAYOUT).to_csv(index=False,header=False).encode('utf-8-sig'),'plantilla_layout.csv','text/csv')

    st.write('Cada casilla debe contener una dirección única, **PASILLO** o **BLOQUEADO**. Podés editar las celdas y agregar filas o columnas usando el tamaño elegido.')
    col1,col2=st.columns(2)
    with col1: filas=st.number_input('Filas del plano',min_value=1,max_value=30,value=len(st.session_state.layout),step=1)
    with col2: columnas=st.number_input('Columnas del plano',min_value=1,max_value=20,value=len(st.session_state.layout.columns),step=1)
    if st.button('Cambiar tamaño del plano'):
        anterior=st.session_state.layout
        matriz=[]
        for i in range(filas):
            matriz.append([str(anterior.iat[i,j]) if i<len(anterior) and j<len(anterior.columns) else 'BLOQUEADO' for j in range(columnas)])
        st.session_state.layout=pd.DataFrame(matriz)
        st.session_state.pop('layout_editor',None)
        st.rerun()
    st.caption('Ejemplo: L09 = dirección habilitada; PASILLO = espacio de circulación; BLOQUEADO = espacio inutilizable. Al agrandar el plano, las celdas nuevas empiezan BLOQUEADO para evitar asignaciones accidentales.')
    layout_edit=st.data_editor(st.session_state.layout,hide_index=True,use_container_width=True,key='layout_editor',column_config={i:st.column_config.TextColumn(f'Columna {i+1}') for i in range(len(st.session_state.layout.columns))})

error=None
try:
    registros=skus_edit.to_dict('records')
    items=preparar_skus(registros,reserva,picking,reposicion)
    grid=[[str(v).strip().upper() for v in row] for row in layout_edit.values.tolist()]
    direcciones=validar_layout(grid,N)
    propuestas=optimizar(items,N,limite=3)
    mejor=propuestas[0]
    asignadas,por_sku=asignar_direcciones(mejor,items,direcciones)
except (ValueError,TypeError,KeyError) as e:
    error=str(e)

with pestanas[1]:
    if error: st.error('Revisá los datos: '+error)
    else:
        st.subheader('Cálculos automáticos')
        st.caption('Esta pestaña muestra cómo se obtiene l y los minutos ahorrados para Nada, Mínimo y Todo. Los valores negativos indican que esa opción aumenta el trabajo.')
        st.latex(r'l=\max\left(\left\lceil\frac{P}{b}\right\rceil,c\right)')
        st.latex(r's=t_{reserva}-t_{picking}\qquad B_{mínimo}=s\,p-c_r\,d\qquad B_{todo}=s\,p')
        st.dataframe(pd.DataFrame([{'SKU':it['SKU'],'P/b':round(it['P']/it['b'],3),'ceil(P/b)':math.ceil(it['P']/it['b']),'c':it['c'],'l':it['l'],'u':it['u'],'Nada (min)':0,'Mínimo (min)':round(it['B_min'],2),'Todo (min)':round(it['B_todo'],2)} for it in items]),hide_index=True,use_container_width=True)
        with st.expander('Ver las cuentas de cada SKU',expanded=True):
            for it in items:
                st.markdown(f"**{it['SKU']}** · l = max(ceil({it['P']:g}/{it['b']:g}), {it['c']}) = **{it['l']}** ubicaciones · Nada: **0** min · Mínimo: ({it['s']:g} × {it['p']}) − ({reposicion:g} × {it['d']:g}) = **{it['B_min']:g} min** · Todo: {it['s']:g} × {it['p']} = **{it['B_todo']:g} min**")
                if it['l']==it['u']: st.caption('En este SKU, mínimo y todo ocupan lo mismo: se utiliza la opción Todo sin reposición interna.')

with pestanas[2]:
    st.subheader('Mejor asignación de espacio')
    if error: st.warning('Corregí primero los datos: '+error)
    else:
        a,b,c,d=st.columns(4)
        a.metric('Ahorro neto semanal',f"{mejor['ahorro']:g} min")
        b.metric('Ubicaciones utilizadas',f"{mejor['ubicaciones']} / {N}")
        c.metric('Ubicaciones libres',str(N-mejor['ubicaciones']))
        base=sum(it['p']*reserva for it in items)
        d.metric('Trabajo semanal estimado',f"{base-mejor['ahorro']:g} min")
        st.dataframe(pd.DataFrame(mejor['decisiones']),hide_index=True,use_container_width=True)
        st.caption(f'Escenario base (todo en reserva): {base:g} minutos por semana. Trabajo con propuesta: {base:g} − {mejor["ahorro"]:g} = {base-mejor["ahorro"]:g} minutos.')
        st.subheader('Comparación de propuestas factibles')
        st.caption('Estas propuestas se generan automáticamente. Más abajo podés armar tres propuestas manuales, como pide el profesor.')
        st.dataframe(pd.DataFrame([{'Propuesta':f'{i+1}','Ubicaciones':p['ubicaciones'],'Ahorro (min/sem)':p['ahorro'],'Decisiones':', '.join(f"{d['SKU']}: {d['opcion']}" for d in p['decisiones'])} for i,p in enumerate(propuestas)]),hide_index=True,use_container_width=True)
        import altair as alt
        grafico_df=pd.DataFrame({'Propuesta':[f'Propuesta {i+1}' for i in range(len(propuestas))],'Ahorro semanal':[p['ahorro'] for p in propuestas]})
        grafico=alt.Chart(grafico_df).mark_bar(cornerRadiusTopLeft=5,cornerRadiusTopRight=5).encode(
            x=alt.X('Propuesta:N',sort=None,title=None,axis=alt.Axis(labelAngle=0)),
            y=alt.Y('Ahorro semanal:Q',title='Minutos ahorrados por semana'),
            color=alt.Color('Propuesta:N',scale=alt.Scale(domain=['Propuesta 1','Propuesta 2','Propuesta 3'],range=['#168B68','#3B82C4','#E59A3A']),legend=None),
            tooltip=['Propuesta:N',alt.Tooltip('Ahorro semanal:Q',format='.2f')]
        ).properties(height=290)
        st.altair_chart(grafico,use_container_width=True)
        st.info('La optimización es exacta: evalúa las alternativas Nada, Mínimo y Todo mediante programación dinámica, respetando N. Ordenar por ahorro por ubicación NO garantiza el óptimo.')
        st.markdown('### Compará tres propuestas propias')
        st.caption('Seleccioná Nada, Mínimo o Todo para cada SKU. Se verifican las ubicaciones y el ahorro de cada propuesta, incluso si no es factible.')
        columnas=st.columns(3)
        alternativas=[]
        for k,col in enumerate(columnas,1):
            with col:
                st.markdown(f'**Propuesta {k}**')
                decision=[]
                for it in items:
                    nombres=[x[0] for x in it['opciones']]
                    predeterminado={1:{'A':'Todo','B':'Todo','C':'Mínimo'},2:{'A':'Mínimo','B':'Todo','C':'Mínimo','E':'Todo'},3:{'A':'Mínimo','B':'Mínimo','C':'Mínimo','E':'Todo','F':'Todo'}}.get(k,{})
                    elegido=st.selectbox(it['SKU'],nombres,index=nombres.index(predeterminado.get(it['SKU'],'Nada')) if predeterminado.get(it['SKU'],'Nada') in nombres else 0,key=f'prop_{k}_{it["SKU"]}')
                    decision.append(next(x for x in it['opciones'] if x[0]==elegido))
                lugares=sum(x[1] for x in decision)
                ahorro=sum(x[2] for x in decision)
                alternativas.append({'Propuesta':k,'Ubicaciones':lugares,'Ahorro (min)':round(ahorro,2),'Estado':'Válida' if lugares<=N else 'Supera capacidad'})
                (st.success if lugares<=N else st.error)(f'{lugares}/{N} ubicaciones · {ahorro:g} min/sem')
        st.dataframe(pd.DataFrame(alternativas),hide_index=True,use_container_width=True)


with pestanas[3]:
    if error: st.warning('Corregí primero los datos: '+error)
    else:
        st.subheader('Asignación física de direcciones')
        st.info('**Cómo leer el plano:** cada rectángulo es una casilla física. El código L01, L02, etc. es la dirección; la letra grande indica el SKU. PASILLO y BLOQUEADO nunca reciben productos. Las casillas LIBRE están disponibles pero no ocupadas.')
        st.caption('Regla: ordenar SKU por p descendente (empates por código); ocupar primero las direcciones de filas inferiores, de izquierda a derecha. Solo se utilizan N direcciones habilitadas.')
        colores=['#CDE9F8','#D5F4DC','#FFE5BF','#E8DBFF','#FAD9E5','#F8F0BD','#D8E8E5','#E3E7ED']
        color_sku={it['SKU']:colores[i%len(colores)] for i,it in enumerate(items)}
        for i,row in enumerate(grid):
            cols=st.columns(len(row),gap='small')
            for j,celda in enumerate(row):
                with cols[j]:
                    if celda in ('PASILLO','BLOQUEADO'):
                        fondo='#E5E7EB' if celda=='PASILLO' else '#B8BEC8'
                        st.markdown(f'<div class="celda" style="background:{fondo};color:#334155"><div class="direccion">Fila {i+1} · C{j+1}</div><div class="sku" style="font-size:.83rem">{celda}</div></div>',unsafe_allow_html=True)
                    else:
                        sku=asignadas.get(celda)
                        habilitada=celda in direcciones
                        fondo=color_sku[sku] if sku else ('#F1F5F9' if habilitada else '#D7DBE1')
                        etiqueta=sku if sku else ('LIBRE' if habilitada else 'NO HABILITADA')
                        st.markdown(f'<div class="celda" style="background:{fondo};color:#1e293b"><div class="direccion">{html.escape(celda)}</div><div class="sku" style="font-size:{"1.3rem" if sku else ".72rem"}">{html.escape(etiqueta)}</div></div>',unsafe_allow_html=True)
        st.markdown('**Leyenda del plano**')
        leyenda=st.columns(min(len(items),6))
        for k,it in enumerate(items):
            with leyenda[k%len(leyenda)]:
                st.markdown(f'<div style="background:{colores[k%len(colores)]};color:#172334;padding:8px;border-radius:8px;text-align:center;font-weight:700">SKU {html.escape(it["SKU"])}</div>',unsafe_allow_html=True)
        st.caption('Gris claro: pasillo / libre. Gris oscuro: bloqueado o no habilitado. La regla de ubicación se aplica de forma uniforme y no modifica el ahorro del modelo.')
        st.markdown('**Direcciones asignadas por SKU**')
        st.dataframe(pd.DataFrame([{'SKU':k,'Direcciones':', '.join(v) if v else 'En reserva','Cantidad':len(v)} for k,v in por_sku.items()]),hide_index=True,use_container_width=True)
        st.caption('Comprobación: el número de direcciones de cada SKU debe coincidir exactamente con las ubicaciones de su decisión Nada, Mínimo o Todo. Una dirección solo puede aparecer una vez.')

with pestanas[4]:
    st.subheader('Validación y exportación')
    st.caption('Usá esta pestaña para demostrar que el programa cumple las restricciones. Luego probá otro almacén y exportá el resultado para el informe.')
    if error: st.warning('Corregí primero los datos: '+error)
    else:
        comprobaciones=[
            ('No se supera la capacidad',mejor['ubicaciones']<=N),
            ('Cada SKU recibe 0, l o u',all(x['ubicaciones'] in (0,next(it['l'] for it in items if it['SKU']==x['SKU']),next(it['u'] for it in items if it['SKU']==x['SKU'])) for x in mejor['decisiones'])),
            ('Las direcciones no se repiten',len(asignadas)==len(set(asignadas))),
            ('El plano coincide con el espacio asignado',len(asignadas)==mejor['ubicaciones']),
            ('No se asigna a PASILLO o BLOQUEADO',all(d in direcciones for d in asignadas)),
        ]
        for nombre,ok in comprobaciones: st.write(('✅' if ok else '❌')+' '+nombre)
        st.markdown('**Prueba de referencia X (según la consigna):** p=50, d=8, P=0.8, b=1, c=1, u=3; s=1 y reposición=3 → l=1; Mínimo=26 min; Todo=50 min.')
        st.markdown('**Segundo almacén:** usá el botón siguiente para cargar un caso distinto con 4 SKU y una casilla BLOQUEADO. También podés importar tus propios archivos.')
        st.button('🧪 Cargar segundo almacén de prueba',on_click=cargar_segundo)
        buffer=io.BytesIO()
        with pd.ExcelWriter(buffer,engine='openpyxl') as writer:
            pd.DataFrame(registros).to_excel(writer,sheet_name='Datos',index=False)
            pd.DataFrame([{k:v for k,v in it.items() if k!='opciones'} for it in items]).to_excel(writer,sheet_name='Calculos',index=False)
            pd.DataFrame(mejor['decisiones']).to_excel(writer,sheet_name='Optimo',index=False)
            pd.DataFrame([{'Propuesta':i+1,'Ubicaciones':p['ubicaciones'],'Ahorro':p['ahorro']} for i,p in enumerate(propuestas)]).to_excel(writer,sheet_name='Comparacion',index=False)
            pd.DataFrame(grid).to_excel(writer,sheet_name='Layout',header=False,index=False)
            pd.DataFrame([{'SKU':k,'Direcciones':', '.join(v)} for k,v in por_sku.items()]).to_excel(writer,sheet_name='Direcciones',index=False)
        st.download_button('📥 Descargar resultados en Excel',data=buffer.getvalue(),file_name='resultados_picking.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        st.download_button('Descargar plantilla de layout (CSV)',data=pd.DataFrame(DEFAULT_LAYOUT).to_csv(index=False,header=False).encode('utf-8-sig'),file_name='plantilla_layout.csv',mime='text/csv')
        st.download_button('Descargar plantilla de SKU (CSV)',data=pd.DataFrame(DEFAULT_SKUS).to_csv(index=False).encode('utf-8-sig'),file_name='plantilla_sku.csv',mime='text/csv')
