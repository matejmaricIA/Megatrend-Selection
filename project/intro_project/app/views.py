
import json
import uuid

from django.db.utils import IntegrityError
from django.http import HttpResponse
from django.http.response import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from app.utils import delete_embeddings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

import celery
from celery.result import AsyncResult
from app.db_serializers import ItemSerializer
from app.models import Category, Item
from app.tasks import classify_similar, extract_features


url = 'http://project_tf_serving_1:8501/v1/models/soda_classifier:predict'


class ListItems(APIView):

    def post(self, request):
        data = request.data

        if 'itemName' in data.keys():

            item_name = data['itemName']
            base64img = data['imageBase64']
            category_name = data['categoryName']

            try:
                category = Category.objects.get(name = category_name)
            except Category.DoesNotExist:
                return JsonResponse({'message': 'Category does not exist.'}, status = status.HTTP_404_NOT_FOUND)

            extract_features_task = extract_features.delay(base64img, item_name)

            while True:
                if extract_features_task.status == celery.states.FAILURE:
                    return Response(status = 500)
                elif extract_features_task.status == celery.states.SUCCESS:

                    item_uuid = str(uuid.uuid1())

                    item = Item.objects.create(uuid = item_uuid, name = item_name, category = category)
                    item.save()

                    return Response(status = 201)
        
        elif 'n' in data.keys():

            n = int(data['n'])
            base64img = data['imageBase64']

            classify_similar_task = classify_similar.delay(base64img, n)

            while True:
                if classify_similar_task.status == celery.states.FAILURE:
                    return Response(status = 500)
                
                elif classify_similar_task.status == celery.states.SUCCESS:
                    
                    predictions = AsyncResult(classify_similar_task.id).get()

            
                    return Response(predictions, status = status.HTTP_200_OK)

        else:
            return Response(status = 404)
        

    def get(self, request):

        items = Item.objects.all()
        data = []

        for item in items:
            #item_serializer = ItemSerializer(item)
            data.append({'name': item.name, 'uuid': item.uuid, 'category': item.category.name}) 
        return Response(json.dumps(data))

    def delete(self, request):
        #data = json.loads(request.body)
        data = request.data
        try:
            item = Item.objects.get(uuid = data['uuid'])
        except Item.DoesNotExist:
                return JsonResponse({'message': 'Item does not exist.'}, status = status.HTTP_404_NOT_FOUND)

        item_name = item.name

        items = Item.objects.filter(name = item_name)

        items.delete()
        delete_embeddings(item_name)
        return JsonResponse({'message': 'Item {0} was deleted successfully.'.format(item_name)}, status = status.HTTP_204_NO_CONTENT)

    def put(self, request):
        data = request.data
        try:
            item = Item.objects.get(uuid = data['uuid'])
        except Item.DoesNotExist:
            return JsonResponse({'message': 'Item does not exist.'}, status = status.HTTP_404_NOT_FOUND)

        if 'name' in data.keys():
            item.name = data['name']
            item.save()

        elif 'category' in data.keys():
            try:
                category = Category.objects.get(name = data['category'])
            
            except Category.DoesNotExist:
                return JsonResponse({'message': 'The category you are trying to update does not exist.'}, status = status.HTTP_404_NOT_FOUND)

            item.category = category
            item.save()

        return JsonResponse({'message': 'Item updated.'}, status = 201)



class ListCategories(APIView):

    def get(self, request):
        
        categories = Category.objects.all()
        data = []
        for ct in categories:
            data.append({'uuid': ct.uuid, 'name': ct.name})
        
        return Response(json.dumps(data))

    def post(self, request):

        data = request.data

        category_name = data['categoryName']
        category_uuid = uuid.uuid1()

        try:
            Category.objects.create(uuid = category_uuid, name = category_name)

        except IntegrityError:
            return JsonResponse({'message': 'The category already exists.'}, status = status.HTTP_400_BAD_REQUEST)

        
        return JsonResponse({'message': 'Category added.'}, status = 201)
