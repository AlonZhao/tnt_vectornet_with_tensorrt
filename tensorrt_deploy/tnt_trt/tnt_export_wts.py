'''
Author: zhanghao
LastEditTime: 2023-04-18 14:45:41
FilePath: /my_vectornet_github/tensorrt_deploy/tnt_trt/tnt_export_wts.py
LastEditors: zhanghao
Description: 
'''
import torch
import pickle
import torch.nn as nn
from tqdm import tqdm
import torch.nn.functional as F

from model.layers.mlp import MLP
from model.layers.subgraph import SubGraph
from model.layers.global_graph import GlobalGraph

from model.layers.target_prediction import TargetPred
from model.layers.motion_etimation import MotionEstimation
from model.layers.scoring_and_selection import TrajScoreSelection


class TNTExport(nn.Module):
    def __init__(self,
                horizon=30,
                in_channels=6,
                k=6,
                m=50,
                num_subgraph_layers=3,
                num_global_graph_layer=1,
                subgraph_width=64,
                global_graph_width=64,
                target_pred_hid=64,
                motion_esti_hid=64,
                score_sel_hid=64,
                device=torch.device("cpu")
                ):
        super(TNTExport, self).__init__()
        # some params
        self.device = device
        self.k = k
        self.m = m
        self.horizon = horizon
        self.out_channels = 2
        self.num_subgraph_layers = num_subgraph_layers
        self.global_graph_width = global_graph_width
        self.target_pred_hid = target_pred_hid
        self.motion_esti_hid = motion_esti_hid
        self.score_sel_hid = score_sel_hid

        # subgraph feature extractor
        self.subgraph = SubGraph(
            in_channels, num_subgraph_layers, subgraph_width)

        # global graph
        self.global_graph = GlobalGraph(self.subgraph.out_channels + 2,
                                        self.global_graph_width,
                                        num_global_layers=num_global_graph_layer)

        self.target_pred_layer = TargetPred(
            in_channels=global_graph_width,
            hidden_dim=target_pred_hid,
            m=m,
            device=device
        )
        self.motion_estimator = MotionEstimation(
            in_channels=global_graph_width,
            horizon=horizon,
            hidden_dim=motion_esti_hid
        )
        self.traj_score_layer = TrajScoreSelection(
            feat_channels=global_graph_width,
            horizon=horizon,
            hidden_dim=score_sel_hid,
            device=self.device
        )

    def forward(self, x, cluster, id_embedding, target_candidate):
        # print("x: \n", x)
        # print("cluster: \n", cluster)
        sub_graph_out = self.subgraph(x, cluster)
        # print("sub_graph_out: \n", sub_graph_out)

        x = torch.cat([sub_graph_out, id_embedding], dim=1).unsqueeze(0)
        global_feat = self.global_graph(x, valid_lens=None)

        target_feat = global_feat[:, 0]
        # print("target_feat: \n", target_feat)
        target_prob, offset = self.target_pred_layer(target_feat, target_candidate)

        _, indices = target_prob.topk(self.m, dim=0)
        target_pred_se, offset_pred_se = target_candidate[indices], offset[indices]
        target_loc_se = (target_pred_se + offset_pred_se).view(self.m, 2)

        trajs = self.motion_estimator(target_feat, target_loc_se)

        scores = self.traj_score_layer(target_feat, trajs)

        return trajs, scores


    def load_ckpt(self, ckpt_path):
        """
        Convert trained model's state_dict and load in.
        """
        weights_dict = torch.load(ckpt_path, map_location=self.device)
        new_weights_dict = {}
        for k, v in weights_dict.items():
            if "aux_mlp" in k:
                continue
            elif "backbone." in k:
                new_k = k.replace("backbone.", "")
                new_weights_dict[new_k] = v
            else:
                new_weights_dict[k] = v

        self.load_state_dict(new_weights_dict)
        print("Success load state dict from: ", ckpt_path)


def save_weights(model, wts_file):
    import struct
    print(f'Writing into {wts_file}')
    with open(wts_file, 'w') as f:
        f.write('{}\n'.format(len(model.state_dict().keys())))
        for k, v in model.state_dict().items():
            vr = v.reshape(-1).cpu().numpy()
            f.write('{} {} '.format(k, len(vr)))
            for vv in vr:
                f.write(' ')
                f.write(struct.pack('>f', float(vv)).hex())
            f.write('\n')
            

def load_tnt(ckpt_path, num_features=6, horizon=30):
    model = TNTExport(in_channels=num_features, horizon=horizon)
    model.load_ckpt(ckpt_path)
    model.eval()
    return model


if __name__ == "__main__":
    SEED = 0
    torch.manual_seed(SEED)
    torch.cuda.manual_seed(SEED)
    
    ckpt = "weights/sg_best_TNT.pth"
    wts = "tensorrt_deploy/tnt_trt/tnt.wts"

    model = load_tnt(ckpt)
    # print(model)

    test_pkl = "tensorrt_deploy/vectornet_trt/src/data/data_seq_40050_features.pkl"
    test_data = pickle.load(open(test_pkl, "rb"))
    x = test_data["x"]
    cluster = test_data["cluster"].long()
    id_embedding = test_data["identifier"]
    target_candidate = test_data['candidate']

    model.cuda()
    with torch.no_grad():
        trajs, scores = model(x.cuda(), 
                              cluster.cuda(), 
                              id_embedding.cuda(), 
                              target_candidate.cuda())
        print(trajs)
        # print(trajs.shape)
        print(scores)
        # print(scores.shape)

    save_weights(model, wts)

