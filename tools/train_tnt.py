'''
Author: zhanghao
LastEditTime: 2023-06-29 14:47:17
FilePath: /my_vectornet_github/tools/train_tnt.py
LastEditors: zhanghao
Description: 
'''
import os
import glob
import json
import argparse
from loguru import logger
from datetime import datetime
from trainer.tnt_trainer import TNTTrainer
from trainer.utils.logger import setup_logger
from dataset.sg_dataloader import SGTrajDataset, collate_list
from dataset.data_augment import *

@logger.catch
def train(n_gpu, args):
    # init output dir
    time_stamp = datetime.now().strftime("%m_%d_%H_%M")
    output_dir = os.path.join(args.output_dir, time_stamp)
    if not args.multi_gpu or (args.multi_gpu and n_gpu == 0):
        if os.path.exists(output_dir) and len(os.listdir(output_dir)) > 0:
            raise Exception("The output folder does exists and is not empty! Check the folder:%s"%output_dir)
        else:
            os.makedirs(output_dir)
        # # dump the args
        # with open(os.path.join(output_dir, 'conf.json'), 'w') as fp:
        #     json.dump(vars(args), fp, indent=4, separators=(", ", ": "))
    
    setup_logger(
            output_dir,
            distributed_rank=0,
            filename="train_log.txt",
            mode="a",
        )

    logger.info("Start training tnt...")
    logger.info("Configs: \n{}\n".format(args))
    
    train_path_list = glob.glob(args.data_root + "/*train")
    val_path_list = glob.glob(args.data_root + "/*val")
    
    augmentation = TrainAugmentation() if args.augment else None
    train_set = SGTrajDataset(
        train_path_list, 
        in_mem=args.on_memory, 
        num_features=args.num_features, 
        augmentation = augmentation
    )
    val_set = SGTrajDataset(
        val_path_list, 
        in_mem=args.on_memory, 
        num_features=args.num_features
    )

    # init trainer
    trainer = TNTTrainer(
        trainset=train_set,
        evalset=val_set,
        testset=val_set,
        collate_fn=collate_list,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        lr=args.l_rate,
        warmup_epoch=args.warmup_epoch,
        lr_decay_rate=args.lr_decay_rate,
        lr_update_freq=args.lr_update_freq,
        weight_decay=args.adam_weight_decay,
        betas=(args.adam_beta1, args.adam_beta2),
        num_global_graph_layer=args.num_glayer,
        aux_loss=args.aux_loss,
        with_cuda=args.with_cuda,
        cuda_device=n_gpu,
        multi_gpu=args.multi_gpu,
        save_folder=output_dir,
        log_freq=args.log_freq,
        ckpt_path=args.resume_checkpoint if hasattr(args, "resume_checkpoint") and args.resume_checkpoint else None,
        model_path=args.resume_model if hasattr(args, "resume_model") and args.resume_model else None,
        K=args.k_select,
        M=args.m_select
    )

    # training
    for iter_epoch in range(args.n_epoch):
        trainer.train(iter_epoch)
        trainer.eval(iter_epoch)

    trainer.eval_save_model("final")
    trainer.test()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("-d", "--data_root", required=False, type=str, default="/home/jovyan/zhdata/TRAJ/EXP8_Heading_Diamond_DIM10_BALANCE/",
                        help="root dir for datasets")
    parser.add_argument("-o", "--output_dir", required=False, type=str, default="work_dir/tnt/",
                        help="dir to save checkpoint and model")
    parser.add_argument("--log_freq", type=int, default=5,
                        help="printing loss every n iter: setting n")
    
    
    parser.add_argument("-b", "--batch_size", type=int, default=4096,
                        help="number of batch_size")
    parser.add_argument("-e", "--n_epoch", type=int, default=200,
                        help="number of epochs")
    
    
    parser.add_argument("-lr", "--l_rate", type=float, default=0.04, help="learning rate of adam")
    parser.add_argument("-we", "--warmup_epoch", type=int, default=10,
                        help="the number of warmup epoch with initial learning rate, after the learning rate decays")
    parser.add_argument("-luf", "--lr_update_freq", type=int, default=20,
                        help="learning rate decay frequency for lr scheduler")
    parser.add_argument("-ldr", "--lr_decay_rate", type=float, default=0.8, help="lr scheduler decay rate")
    
    
    parser.add_argument("-nf", "--num_features", type=int, default=10)
    parser.add_argument("-M", "--m_select", type=int, default=50)
    parser.add_argument("-K", "--k_select", type=int, default=6)
    parser.add_argument("-l", "--num_glayer", type=int, default=1,
                        help="number of global graph layers")
    parser.add_argument("-aux", "--aux_loss", action="store_true", default=False,
                        help="Training with the auxiliary recovery loss")
    
    
    parser.add_argument("-om", "--on_memory", type=bool, default=True, help="Loading on memory: true or false")
    parser.add_argument("-w", "--num_workers", type=int, default=0,
                        help="dataloader worker size")
    
    
    parser.add_argument("-aug", "--augment", action="store_true", default=False,
                        help="training with augment: true, or false")
    parser.add_argument("-c", "--with_cuda", action="store_true", default=True,
                        help="training with CUDA: true, or false")
    parser.add_argument("-m", "--multi_gpu", action="store_true", default=False,
                        help="training with distributed data parallel: true, or false")
    parser.add_argument("-r", "--local_rank", default=0, type=int,
                        help="the default id of gpu")

    
    parser.add_argument("--adam_weight_decay", type=float, default=0.01, help="weight_decay of adam")
    parser.add_argument("--adam_beta1", type=float, default=0.9, help="adam first beta value")
    parser.add_argument("--adam_beta2", type=float, default=0.999, help="adam first beta value")

    
    parser.add_argument("-rc", "--resume_checkpoint", type=str, help="resume a checkpoint for fine-tune")
    parser.add_argument("-rm", "--resume_model", type=str, help="resume a model state for fine-tune")

    
    args = parser.parse_args()
    train(args.local_rank, args)
