import torch
import torch.nn as nn
import torchvision.models as models
from torchvision import transforms


class VegetableClassifier(nn.Module):
    def __init__(self, num_classes=15, pretrained=True):
        super(VegetableClassifier, self).__init__()

        # Используем EfficientNet как базовую модель
        self.model = models.efficientnet_b0(pretrained=pretrained)

        # Заменяем последний слой
        num_features = self.model.classifier[1].in_features
        self.model.classifier = nn.Sequential(
            nn.Dropout(p=0.3, inplace=True),
            nn.Linear(num_features, 512),
            nn.ReLU(),
            nn.BatchNorm1d(512),
            nn.Dropout(p=0.2),
            nn.Linear(512, num_classes)
        )

        # Аугментации для обучения
        self.train_transform = transforms.Compose([
            transforms.RandomResizedCrop(224),
            transforms.RandomHorizontalFlip(),
            transforms.RandomRotation(20),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])

        # Преобразования для инференса
        self.val_transform = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])

    def forward(self, x):
        return self.model(x)

    def predict(self, image_tensor):
        """Предсказание для одного изображения"""
        self.eval()
        with torch.no_grad():
            output = self.forward(image_tensor.unsqueeze(0))
            probabilities = torch.nn.functional.softmax(output, dim=1)
            confidence, predicted = torch.max(probabilities, 1)
        return predicted.item(), confidence.item()


def load_model(model_path="models/best_model.pth", num_classes=15):
    """Загрузка обученной модели"""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = VegetableClassifier(num_classes=num_classes)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.to(device)
    model.eval()

    return model, device


def preprocess_image(image, transform_type='val'):
    """Предобработка изображения для модели"""
    model = VegetableClassifier()
    if transform_type == 'val':
        transform = model.val_transform
    else:
        transform = model.train_transform

    return transform(image).unsqueeze(0)  # Добавляем batch dimension