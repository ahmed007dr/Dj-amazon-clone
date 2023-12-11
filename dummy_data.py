import os ,django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
django.setup()

from faker import Faker
import random
from products.models import Product , Brand , Review

def seed_brand(n):
    fake = Faker()
    #image_list = [f"brand/{i}.jpg" for I in range(1, 11)]
    image=['01.jpg','02.jpg','03.jpg','04.jpg','05.jpg','06.jpg','07.jpg','08.jpg','09.jpg','10.jpg']
    for _ in range(n):
        Brand.objects.create(
            name=fake.name(),
            image=f"brand/{image[random.randint(0,9)]}"
        )
        print(f'{n} brand was add')

def seed_prouducts(n):
    fake = Faker()
    flag_types=['name','sale','feature']
    brands=Brand.objects.all()
    for _ in range(n):
        Product.objects.create(
            name=fake.name(),
            flag = flag_types[random.randint(0,2)],
            price=round(random.uniform(20.99,99.99),2),
            image='f"product/{image[random.randint(0,9)]}"',
            sku=random.randint(100,100000),
            subtitle=fake.text(max_nb_chars=450),
            description=fake.text(max_nb_chars=3000),
            brand=brands[random.randint(0,len(brands)-1)]
        )
        print(f'{n} products was add')

def seed_reviews(n):
    pass


#seed_brand(200)
#seed_prouducts(1500)