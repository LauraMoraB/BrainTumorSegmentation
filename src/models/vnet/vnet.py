import torch.nn as nn
import torch
from torchsummary import summary
import torch.nn.functional as F


def passthrough(x, **kwargs):
    return x


def ELUCons(elu, nchan):
    if elu == "elu":
        return nn.ELU(inplace=True)
    elif elu == "prelu":
        return nn.PReLU(nchan)
    elif elu == "leaky":
        return nn.LeakyReLU(negative_slope=1e-2, inplace=True)
    else:
        return nn.ELU(inplace=True)


def normalization(num_channels, typee):
    if typee == "instance":
        return torch.nn.InstanceNorm3d(num_channels)
    elif typee == "group":
        return torch.nn.GroupNorm(2, num_channels)
    else:
        return torch.nn.BatchNorm3d(num_channels)


class LUConv(nn.Module):
    def __init__(self, nchan, elu):
        super(LUConv, self).__init__()
        self.relu1 = ELUCons(elu, nchan)
        self.conv1 = nn.Conv3d(nchan, nchan, kernel_size=5, padding=2)
        self.bn1 = torch.nn.InstanceNorm3d(nchan)

    def forward(self, x):
        out = self.relu1(self.bn1(self.conv1(x)))
        return out


def _make_nConv(nchan, depth, elu):
    layers = []
    for _ in range(depth):
        layers.append(LUConv(nchan, elu))
    return nn.Sequential(*layers)


class InputTransition(nn.Module):
    def __init__(self, in_channels, num_features, elu):
        super(InputTransition, self).__init__()
        self.num_features = num_features  # 16
        self.in_channels = in_channels

        self.conv1 = nn.Conv3d(self.in_channels, self.num_features, kernel_size=5, padding=2)

        self.bn1 = torch.nn.InstanceNorm3d(self.num_features)

        self.relu1 = ELUCons(elu, self.num_features)

    def forward(self, x):
        out = self.conv1(x)
        repeat_rate = int(self.num_features / self.in_channels)
        out = self.bn1(out)
        x16 = x.repeat(1, repeat_rate, 1, 1, 1)
        return self.relu1(torch.add(out, x16))


class DownTransition(nn.Module):
    def __init__(self, inChans, nConvs, elu, dropout=False):
        super(DownTransition, self).__init__()
        outChans = 2 * inChans
        self.down_conv = nn.Conv3d(inChans, outChans, kernel_size=2, stride=2)
        self.bn1 = torch.nn.InstanceNorm3d(outChans)

        self.do1 = passthrough
        self.relu1 = ELUCons(elu, outChans)
        self.relu2 = ELUCons(elu, outChans)
        if dropout:
            self.do1 = nn.Dropout3d()
        self.ops = _make_nConv(outChans, nConvs, elu)

    def forward(self, x):
        down = self.relu1(self.bn1(self.down_conv(x)))
        out = self.do1(down)
        out = self.ops(out)
        out = self.relu2(torch.add(out, down))
        return out


class UpTransition(nn.Module):
    def __init__(self, inChans, outChans, nConvs, elu, dropout=False):
        super(UpTransition, self).__init__()
        self.up_conv = nn.ConvTranspose3d(inChans, outChans // 2, kernel_size=2, stride=2)

        self.bn1 = torch.nn.InstanceNorm3d(outChans // 2)
        self.do1 = passthrough
        self.do2 = nn.Dropout3d()
        self.relu1 = ELUCons(elu, outChans // 2)
        self.relu2 = ELUCons(elu, outChans)
        if dropout:
            self.do1 = nn.Dropout3d()
        self.ops = _make_nConv(outChans, nConvs, elu)

    def forward(self, x, skipx):
        out = self.do1(x)
        skipxdo = self.do2(skipx)
        out = self.relu1(self.bn1(self.up_conv(out)))
        xcat = torch.cat((out, skipxdo), 1)
        out = self.ops(xcat)
        out = self.relu2(torch.add(out, xcat))
        return out


class OutputTransition(nn.Module):
    def __init__(self, in_channels, classes, elu):
        super(OutputTransition, self).__init__()

        self.classes = classes
        self.conv1 = nn.Conv3d(in_channels, classes, kernel_size=5, padding=2)
        self.bn1 = torch.nn.InstanceNorm3d(classes)

        self.conv2 = nn.Conv3d(classes, classes, kernel_size=1)
        self.relu1 = ELUCons(elu, classes)

        self.softmax = F.softmax

    def forward(self, x):
        # convolve 32 down to channels as the desired classes
        out = self.relu1(self.bn1(self.conv1(x)))
        out = self.conv2(out)

        out_scores = out
        # make channels the last axis
        out_scores = out_scores.permute(0, 2, 3, 4, 1).contiguous()
        # flatten
        out_scores = out_scores.view(out.numel() // self.classes, self.classes)
        out_scores = self.softmax(out_scores, dim=1)

        return out, out_scores


class VNet(nn.Module):
    """
    Implementations based on the Vnet paper: https://arxiv.org/abs/1606.04797
    """

    def __init__(self, elu=True, in_channels=1, classes=4,
                 init_features_maps=16):  # input channels: the four modalities
        super(VNet, self).__init__()
        self.classes = classes
        self.in_channels = in_channels

        self.in_tr = InputTransition(in_channels, init_features_maps, elu=elu)
        self.down_tr32 = DownTransition(init_features_maps, 1, elu)
        self.down_tr64 = DownTransition(init_features_maps * 2, 2, elu, dropout=True)
        self.down_tr128 = DownTransition(init_features_maps * 4, 3, elu, dropout=True)
        self.down_tr256 = DownTransition(init_features_maps * 8, nConvs=2, elu=elu, dropout=True)

        self.up_tr256 = UpTransition(init_features_maps * 16, init_features_maps * 16, 2, elu, dropout=True)
        self.up_tr128 = UpTransition(init_features_maps * 16, init_features_maps * 8, 2, elu, dropout=True)
        # self.up_tr128 = UpTransition(128, 128, 2, elu, dropout=True)
        self.up_tr64 = UpTransition(init_features_maps * 8, init_features_maps * 4, 1, elu, dropout=True)
        self.up_tr32 = UpTransition(init_features_maps * 4, init_features_maps * 2, 1, elu)
        self.out_tr = OutputTransition(init_features_maps * 2, classes, elu)

    def forward(self, x):
        out16 = self.in_tr(x)
        out32 = self.down_tr32(out16)
        out64 = self.down_tr64(out32)
        out128 = self.down_tr128(out64)
        out256 = self.down_tr256(out128)
        out = self.up_tr256(out256, out128)
        out = self.up_tr128(out, out64)
        # out = self.up_tr128(out128, out64)
        out = self.up_tr64(out, out32)
        out = self.up_tr32(out, out16)
        out = self.out_tr(out)
        return out

    def test(self, device='cpu'):
        input_tensor = torch.rand(1, self.in_channels, 32, 32, 32)
        ideal_out = torch.rand(1, self.classes, 32, 32, 32)
        out_pred, _ = self.forward(input_tensor)
        assert ideal_out.shape == out_pred.shape
        summary(self.to(torch.device(device)), (self.in_channels, 32, 32, 32), device=device)
        print("Vnet test is complete")


if __name__ == "__main__":
    vnet = VNet()
    vnet.test()
