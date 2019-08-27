from datetime import datetime
import torch
from torch import nn, optim
from torch.utils import data

from datasets import Modalities, classes
from model import LinearWrapper, PlantFeatureExtractor as FeatureExtractor

epochs = 5
label_lr = 0.01
plant_lr = 0.01
extractor_lr = 0.001

start_date = datetime(2019, 6, 5)
end_date = datetime(2019, 6, 23)
split_cycle = 7
lwir_max_len = 250
vir_max_len = 16

domain_adapt_l = 0.1

modalities = {
    'lwir': {'max_len': lwir_max_len},
    '577nm': {'max_len': vir_max_len},
    '692nm': {'max_len': vir_max_len},
    '732nm': {'max_len': vir_max_len},
    '970nm': {'max_len': vir_max_len},
    'polar': {'max_len': vir_max_len}
}

device = 'cuda' if torch.cuda.is_available() else 'cpu'

dataset = Modalities(
    'Exp0', split_cycle=split_cycle, start_date=start_date, end_date=end_date, **modalities
)
dataloader = data.DataLoader(dataset, batch_size=4, num_workers=2)

feat_ext = FeatureExtractor(*modalities)
label_cls = nn.Sequential(nn.Linear(512, len(classes)), nn.Softmax())
plant_cls = nn.Sequential(nn.Linear(512, 48), nn.Softmax())

criterion = nn.CrossEntropyLoss()

label_opt = optim.Adam(label_cls.parameters(), lr=label_lr)
plant_opt = optim.Adam(plant_cls.parameters(), lr=plant_lr)
ext_opt = optim.Adam(feat_ext.parameters(), lr=extractor_lr)

best_loss = float('inf')
for epoch in range(epochs):
    print(f"epoch {epoch + 1} - ", end='')

    tot_label_loss = 0.
    tot_plant_loss = 0.
    for i, batch in enumerate(dataloader):

        labels = batch['label']
        plants = batch['plant']

        del batch['label']
        del batch['plant']

        label_opt.zero_grad()
        plant_opt.zero_grad()
        ext_opt.zero_grad()

        features: torch.Tensor = feat_ext(**batch)
        features_plants = features.clone()
        features_plants.register_hook(lambda grad: -domain_adapt_l * grad)

        label_out = label_cls(features)
        label_loss = criterion(label_out, labels)

        plant_out = plant_cls(features_plants)
        plant_loss = criterion(plant_out, plants)
        (label_loss + plant_loss).backward()

        label_opt.step()
        ext_opt.step()
        plant_opt.step()

        tot_label_loss += label_loss.item()
        tot_plant_loss += plant_loss.item()

        if i % 6 == 5:
            print(f"{i}. label loss: {tot_label_loss / 6}")
            print(f"{i}. plant loss: {tot_plant_loss / 6}")

            if tot_label_loss < best_loss:
                torch.save({
                    'epoch': epoch,
                    'feat_ext_state_dict': feat_ext.state_dict(),
                    'label_cls_state_dict': label_cls.state_dict(),
                    'plant_cls_state_dict': plant_cls.state_dict(),
                    'loss': tot_label_loss
                }, f'checkpoint')

                best_loss = tot_label_loss

            tot_label_loss = 0.
            tot_plant_loss = 0.
