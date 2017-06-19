import cv2
import numpy as np
import torch.nn as nn
import torch
from torch.utils.data import DataLoader
from torch.autograd import Variable
from data.kgdataset import KgForestDataset, toTensor
from torchvision.transforms import Normalize, Compose, Lambda
import glob
from planet_models.resnet_planet import resnet18_planet, resnet34_planet, resnet50_planet
from planet_models.densenet_planet import densenet161, densenet121, densenet169
from util import predict, f2_score, pred_csv


def default(imgs):
    return imgs


def rotate90(imgs):
    for index, img in enumerate(imgs):
        imgs[index] = cv2.transpose(img, (1, 0, 2))
    return imgs


def rotate180(imgs):
    for index, img in enumerate(imgs):
        imgs[index] = cv2.flip(img, -1)
    return imgs


def rotate270(imgs):
    for index, img in enumerate(imgs):
        img = cv2.transpose(img, (1, 0, 2))
        imgs[index] = cv2.flip(img, -1)
    return imgs


def horizontalFlip(imgs):
    for index, img in enumerate(imgs):
        img = cv2.flip(img, 1)
        imgs[index] = img
    return imgs


def verticalFlip(imgs):
    for index, img in enumerate(imgs):
        img = cv2.flip(img, 0)
        imgs[index] = img
    return imgs


mean = [0.31151703, 0.34061992, 0.29885209]
std = [0.16730586, 0.14391145, 0.13747531]
threshold = [0.23166666666666666, 0.19599999999999998, 0.18533333333333335,
             0.08033333333333334, 0.20199999999999999, 0.16866666666666666,
             0.20533333333333334, 0.27366666666666667, 0.2193333333333333,
             0.21299999999999999, 0.15666666666666665, 0.096666666666666679,
             0.21933333333333335, 0.058666666666666673, 0.19033333333333333,
             0.25866666666666666, 0.057999999999999996]

transforms = [default, rotate90, rotate180, rotate270, verticalFlip, horizontalFlip]
models = [resnet34_planet, resnet50_planet, densenet121, densenet161, densenet169]




# if __name__ == '__main__':
#     img = cv2.imread('images.jpeg')
#     img = cv2.resize(img, (256, 256))
#     img = np.expand_dims(img, axis=0)
#     rotation90 = rotate90(img.copy())[0]
#     rotation180 = rotate180(img.copy())[0]
#     rotation270 = rotate270(img.copy())[0]
#     vertical = verticalFlip(img.copy())[0]
#     horizontal = horizontalFlip(img.copy())[0]
#     cv2.imshow('original', img[0])
#     cv2.imshow('90', rotation90)
#     cv2.imshow('180', rotation180)
#     cv2.imshow('270', rotation270)
#     cv2.imshow('vertical', vertical)
#     cv2.imshow('horizontal', horizontal)
#
#     cv2.waitKey()


# save probabilities to files for debug
def probs(dataloader):
    """
    returns a numpy array of probabilities (n_transforms, n_models, n_imgs, 17)
    use transforms to find the best threshold
    use models to do ensemble method
    """
    n_transforms = len(transforms)
    n_models = len(models)
    n_imgs = dataloader.dataset.num
    imgs = dataloader.dataset.images.copy()
    probabilities = np.empty((n_transforms, n_models, n_imgs, 17))
    for t_idx, transform in enumerate(transforms):
        t_name = str(transform).split()[1]
        dataloader.dataset.images = transform(imgs)
        for m_idx, model in enumerate(models):
            name = str(model).split()[1]
            net = model().cuda()
            net = nn.DataParallel(net)
            net.load_state_dict(torch.load('models/{}.pth'.format(name)))
            net.eval()
            # predict
            m_predictions = predict(net, dataloader)

            # save
            np.savetxt(X=m_predictions, fname='probs/{}_{}.txt'.format(t_name, name))
            probabilities[t_idx, m_idx] = m_predictions
    return probabilities


def find_best_threshold(labels, probabilities):
    threshold = np.zeros(17)

    # iterate over transformations
    for t_idx in range(len(transforms)):
        # iterate over class labels
        t = np.ones(17) * 0.15
        selected_preds = probabilities[t_idx]
        selected_preds = np.mean(selected_preds, axis=0)
        best_thresh = 0.0
        best_score = 0.0
        for i in range(17):
            for r in range(500):
                r /= 500
                t[i] = r
                preds = (selected_preds > t).astype(int)
                score = f2_score(labels, preds)
                if score > best_score:
                    best_thresh = r
                    best_score = score
            t[i] = best_thresh
            print('Transform index {}, score {}, threshold {}, label {}'.format(t_idx, best_score, best_thresh, i))
        print('Transform index {}, threshold {}, score {}'.format(t_idx, t, best_score))
        threshold = threshold + t
    threshold = threshold / len(transforms)
    return threshold




# optimize the results


if __name__ == '__main__':
    # validation = KgForestDataset(
    #     split='validation-3000',
    #     transform=Compose(
    #         [
    #             Lambda(lambda x: toTensor(x)),
    #             Normalize(mean=mean, std=std)
    #         ]
    #     ),
    #     height=256,
    #     width=256
    # )
    # valid_dataloader = DataLoader(validation, batch_size=256, shuffle=False)
    # # print(probs(valid_dataloader))
    # file_names = glob.glob('probs/*.txt')
    # file_names = [name for name in file_names if 'resnet18' not in name]
    # preds = np.empty((len(transforms), len(models), 3000, 17))
    # for t_idx in range(len(transforms)):
    #     for m_idx in range(len(models)):
    #         preds[t_idx, m_idx] = np.loadtxt(file_names[t_idx + m_idx])
    # print(file_names)
    # t = find_best_threshold(labels=validation.labels, probabilities=preds)
    # print(list(t))
    # # print(np.loadtxt('probs/default_densenet121.txt').shape)

    test_dataset = KgForestDataset(
        split='test-61191',
        transform=Compose(
            [
                Lambda(lambda x: toTensor(x)),
                Normalize(mean=mean, std=std)
            ]
        )
    , label_csv=None)

    test_dataloader = DataLoader(test_dataset, batch_size=512)
    preds = np.zeros((61191, 17))
    for index, model in enumerate(models):
        name = str(model).split()[1]
        net = nn.DataParallel(model().cuda())
        net.load_state_dict(torch.load('models/{}.pth'.format(name)))
        pred = predict(dataloader=test_dataloader, net=net)
        preds = preds + pred

    preds = preds/len(models)
    pred_csv(predictions=preds, threshold=threshold, name='ensembles')