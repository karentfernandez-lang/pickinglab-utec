import unittest
from motor import *

class Pruebas(unittest.TestCase):
    def test_x(self):
        x=preparar_skus([{'SKU':'X','p':50,'d':8,'P':.8,'b':1,'c':1,'u':3}],2,1,3)[0]
        self.assertEqual((x['l'],x['B_min'],x['B_todo']),(1,26,50))
        self.assertEqual([o[1] for o in x['opciones']],[0,1,3])
    def test_comun(self):
        items=preparar_skus(DEFAULT_SKUS,2,1,3)
        self.assertEqual([x['l'] for x in items],[1,2,1,1,1,1])
        r=optimizar(items,8)
        self.assertLessEqual(r[0]['ubicaciones'],8)
        self.assertGreaterEqual(r[0]['ahorro'],335)
        dirs=validar_layout(DEFAULT_LAYOUT,8)
        a,_=asignar_direcciones(r[0],items,dirs)
        self.assertEqual(len(a),r[0]['ubicaciones'])
    def test_invalidos(self):
        with self.assertRaises(ValueError): preparar_skus([dict(DEFAULT_SKUS[0],b=0)],2,1,3)
        with self.assertRaises(ValueError): preparar_skus([dict(DEFAULT_SKUS[0],c=1.5)],2,1,3)
        with self.assertRaises(ValueError): preparar_skus([dict(DEFAULT_SKUS[0],P=10)],2,1,3)
        with self.assertRaises(ValueError): preparar_skus(DEFAULT_SKUS+[DEFAULT_SKUS[0]],2,1,3)
        with self.assertRaises(ValueError): validar_layout([['L01','L01']],2)
        with self.assertRaises(ValueError): validar_layout(DEFAULT_LAYOUT,9)
    def test_otro_almacen(self):
        grid=[['X01','PASILLO','X02'],['BLOQUEADO','X03','X04']]
        dirs=validar_layout(grid,3)
        items=preparar_skus([{'SKU':'Q','p':25,'d':2,'P':.4,'b':1,'c':1,'u':2}, {'SKU':'R','p':10,'d':1,'P':.7,'b':1,'c':1,'u':2}],3,1,2)
        sol=optimizar(items,3)[0]
        a,_=asignar_direcciones(sol,items,dirs)
        self.assertLessEqual(len(a),3)
        self.assertNotIn('BLOQUEADO',a)
    def test_optimo_exhaustivo(self):
        from itertools import product
        items=preparar_skus(DEFAULT_SKUS,2,1,3)
        maximo=max(sum(x[2] for x in combo) for combo in product(*(i['opciones'] for i in items)) if sum(x[1] for x in combo)<=8)
        self.assertAlmostEqual(optimizar(items,8)[0]['ahorro'],maximo)

if __name__=='__main__':unittest.main()
