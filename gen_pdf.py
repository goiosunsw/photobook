import glob
import os
import sys
import argparse
from PIL import Image, ExifTags
from fpdf import FPDF

def get_image_aspect_ratio(path):
    im = Image.open(path)
    return im.size[0]/im.size[1]


class Converter(object):
    def __init__(self, temp_path='._gallery_temp'):
        self.temp_path = temp_path
        try:
            os.mkdir(temp_path)
        except FileExistsError:
            pass
        
    def read_image(self, filename):
        self.image = Image.open(filename)

    def generate_temp_image(self, filename):
        path = os.path.join(self.temp_path,filename) 
        image = self.image.convert("RGB")
        image.save(path)
        self.image.close()
        image.close()
        return path

    def get_exif_dict(self):
        self.exif=dict()

        try:
            exif_raw = self.image._getexif().items()
        except AttributeError:
            exif_raw = {}

        for k,v in exif_raw:
            try:
                self.exif[ExifTags.TAGS[k]]=v 
            except KeyError:
                self.exif[k]=v
        return self.exif

    def apply_exif_rotation(self):
        exif = self.get_exif_dict()
        try:
            if exif['Orientation'] == 3:
                self.image=self.image.rotate(180, expand=True)
            elif exif['Orientation'] == 6:
                self.image=self.image.rotate(270, expand=True)
            elif exif['Orientation'] == 8:
                self.image=self.image.rotate(90, expand=True)
        except KeyError:
            pass

    def resample(self,h,dpi=150):
        h_px = int(h/2.56*dpi)
        
        cur_w = self.image.size[0]
        cur_h = self.image.size[1]

        w_px = int(cur_w/cur_h*h_px)

        try:
            self.image = self.image.resize((w_px,h_px),3)
        except KeyError:
            pass

    def cleanup(self):
        import shutil
        shutil.rmtree(self.temp_path)

class Gallery(object):
    def __init__(self, output_file=None, height=None, marg=0.5, dpi=300,
            with_label=False, orientation='P', paper_size='A4'):
        # print("paper orientation: "+orientation)
        pdf = FPDF(orientation,'cm',paper_size)
        self.pdf = pdf
        print("Paper W x H: {:.1f} x {:.1f}".format(pdf.w,pdf.h))
        self.pdf.set_font("Arial",size=8)
        self.text_h = 0.3
        if not height:
            height = self.pdf.h/2.5
        self.height = height
        self.pos = [1.0,1.0]
        self.max_pos = [pdf.w-pdf.r_margin, pdf.h-pdf.b_margin]
        self.marg = marg
        if with_label:
            self.marg += self.text_h
        self.output_file = output_file
        self.dpi = dpi
        self.conv = Converter()
        self.label = with_label
        self.n_photos_on_page = 0


    def place_rect(self, w, h):
        x = self.pos[0]
        y = self.pos[1]
        self.n_photos_on_page += 1
        if x+w > self.max_pos[0]:
            sys.stderr.write("New line\n")
            x = self.pdf.l_margin
            y = self.pos[1] + h + self.marg
        if y+h > self.max_pos[1]:
            sys.stderr.write("New page\n")
            self.pdf.add_page()
            y = self.pdf.t_margin
            self.n_photos_on_page = 0
        self.pos = [x+w+self.marg,y]
        return x,y

    def converted_file(self, file, h, dpi=None):
        self.conv.read_image(file)
        self.conv.apply_exif_rotation()
        if dpi is not None:
            self.conv.resample(h,dpi=dpi)
        outfile = os.path.splitext(os.path.split(file)[-1])[0]
        outfile += '.jpg'
        new_file = self.conv.generate_temp_image(outfile)
        return new_file

    def add_picture_from_file(self, file, h=None, w=None, dpi=None):
        name = os.path.splitext(os.path.split(file)[-1])[0]
        if h is None:
            h = self.height
        if dpi:
            try:
                file=self.converted_file(file,h,dpi=dpi)
                sys.stderr.write("Temp saved in %s\n"%file)
            except OSError:
                sys.stderr.write("File not converted: %s\n"%file)
        if w is None:
            rat = get_image_aspect_ratio(file)
            w = self.height*rat

        x,y = self.place_rect(w, h)
        self.pdf.image(file,x=x, y=y, 
            h=h, w=w)
        if self.label:
            self.pdf.text(x=x,y=y+h+self.text_h,txt=name)

    def new_page(self):
        if self.n_photos_on_page > 0:
            #self.pdf.add_page()
            self.pos = [ii for ii in self.max_pos]
        # self.pos = [self.pdf.l_margin,
        #            self.pdf.t_margin]
        return

    def generate_tree(self, path, extensions=['png','jpg','jpeg'], dir_break=False):
        pdf = self.pdf
        pdf.add_page()
        for root, dirs, files in os.walk(path):
            for filename in files:
                base, ext = os.path.splitext(filename)
                ext = ext.lower()[1:]
                if ext in extensions:
                    sys.stderr.write("adding %s\n"%filename)
                    file = os.path.join(root,filename)
                    try:
                        self.add_picture_from_file(file,dpi=self.dpi)
                    except(IOError,OSError):
                        sys.stderr.write('File error: %s'%file)
                        continue
                else:
                    sys.stderr.write("skipping %s\n"%filename)
            if dir_break:
                self.new_page()
        if not self.output_file:
            basename = os.path.split(path.strip(os.sep))[-1]
            output_file = basename+'.pdf'
        else:
            output_file = self.output_file
        pdf.output(output_file,'F')
        self.conv.cleanup()

def generate_gallery(path, height=0.0,**kwargs):
    try:
        dir_break = kwargs['dir_break']
    except KeyError:
        dir_break = False

    del(kwargs['dir_break'])

    if height>0:
        sys.stderr.write("Height set to %f cm\n"%height)
        pp=Gallery(height=height,**kwargs)
    else:
        pp = Gallery(**kwargs)
    pp.generate_tree(path, dir_break=dir_break)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument("-s", "--subfolders", action="store_true", default=False, 
            help="build one PDF per folder in path")
    ap.add_argument("-l", "--labels", action="store_true", default=False, 
            help="add labels per picture")
    ap.add_argument("-d", "--dir-break", action="store_true", default=False, 
            help="page break at each new directory")
    ap.add_argument("-y", "--height", nargs="?", type=float, default=0.0, 
            help="picture height (cm)")
    ap.add_argument("-L", "--landscape", action="store_true", default=False,
            help="landscape orientation")
    ap.add_argument("-S", "--paper-size", nargs="?", default="A4",
            help="paper size (e.g. A4, letter...)")
    ap.add_argument("path", nargs="?", default=".",
            help="base path to walk into and look for images")

    args = ap.parse_args()

    if args.landscape:
        orientation = "L"
    else:
        orientation = "P"

    if args.subfolders:
        dirs = next(os.walk(args.path))[1]
        for dd in dirs:
            generate_gallery(dd, with_label=args.labels, height=args.height,
                    dir_break=args.dir_break, orientation=orientation,
                    paper_size=args.paper_size)

    else:
        generate_gallery(args.path, with_label=args.labels, height=args.height,
                    dir_break=args.dir_break, orientation=orientation,
                    paper_size=args.paper_size)
