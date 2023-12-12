docker run --name $CONTAINER_NAME -dit --restart unless-stopped -d -p 127.0.0.1:$PORT:5000 $IMAGE_TO_BUILD
echo Закончили