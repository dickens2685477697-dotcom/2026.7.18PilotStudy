import cv2
import glob
import os

current_path = os.path.realpath(__file__)
current_dir = os.path.dirname(current_path)

li_jpg_files = glob.glob(current_dir + "/*.jpg")

for jpg_file in li_jpg_files:
    img = cv2.imread(jpg_file, cv2.IMREAD_GRAYSCALE)
    img = cv2.bitwise_not(img)

    jpg_filename = os.path.basename(jpg_file)
    jpg_name, jpg_ext = os.path.splitext(jpg_filename)

    png_filename = jpg_name + "_inverted.png"
    cv2.imwrite(png_filename, img)
